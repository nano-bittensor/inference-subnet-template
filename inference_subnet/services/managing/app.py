from fastapi import FastAPI, HTTPException, Depends
from loguru import logger
from inference_subnet.services.managing.schemas import (
    ConsumeRequest,
    UpdateScoreRequest,
    MinerSamplingResponse,
    ScoreResponse,
)
from inference_subnet.settings import SETTINGS
import asyncio
from redis.asyncio import Redis
from httpx import AsyncClient, HTTPError
from inference_subnet.services.sidecar_subtensor.schemas import NodeInfoList
import numpy as np
from typing import Dict, Any
import time

from inference_subnet.services.managing.rate_limit_manager import RateLimitManager
from inference_subnet.services.managing.score_manager import ScoreManager


class ManagingService:
    def __init__(self):
        self.app = FastAPI(title="Inference Subnet Managing Service")
        self.redis = Redis(
            host=SETTINGS.redis.host,
            port=SETTINGS.redis.port,
            db=SETTINGS.redis.db,
            decode_responses=True,
        )
        self.rate_limit_manager = RateLimitManager(self.redis)
        self.score_manager = ScoreManager(self.redis)
        self._node_infos_cache = None
        self._node_infos_timestamp = 0
        self._cache_ttl = 600
        self.setup_routes()
        self.setup_events()

    def setup_routes(self):
        self.app.post("/api/consume", response_model=MinerSamplingResponse)(
            self.consume
        )
        self.app.post("/api/update-score")(self.update_score)
        self.app.get("/api/get-scores", response_model=ScoreResponse)(self.get_scores)
        self.app.get("/api/health")(self.health_check)

    def setup_events(self):
        self.app.on_event("startup")(self.startup_event)

    async def get_redis(self) -> Redis:
        """Dependency to get Redis connection"""
        return self.redis

    async def get_rate_limit_manager(self) -> RateLimitManager:
        """Dependency to get RateLimitManager instance"""
        return self.rate_limit_manager

    async def get_score_manager(self) -> ScoreManager:
        """Dependency to get ScoreManager instance"""
        return self.score_manager

    async def fetch_node_infos(self) -> NodeInfoList:
        """Fetch node information from the sidecar service with caching"""
        current_time = time.time()

        if (
            self._node_infos_cache is not None
            and (current_time - self._node_infos_timestamp) < self._cache_ttl
        ):
            logger.debug("Using cached node_infos")
            return self._node_infos_cache
        try:
            async with AsyncClient(
                base_url=SETTINGS.substrate_sidecar.base_url,
                timeout=SETTINGS.substrate_sidecar.request_timeout,
            ) as client:
                response = await client.get("/api/nodes")
                if response.status_code != 200:
                    logger.error(f"Failed to fetch node info: {response.text}")
                    raise HTTPException(
                        status_code=502,
                        detail="Failed to fetch node information from subtensor sidecar",
                    )

                # Update cache with fresh data
                self._node_infos_cache = NodeInfoList.model_validate_json(response.text)
                self._node_infos_timestamp = current_time
                logger.debug("Node info cache updated")

                return self._node_infos_cache
        except HTTPError as e:
            logger.error(f"HTTP error when fetching node info: {str(e)}")
            raise HTTPException(
                status_code=502,
                detail=f"Communication error with subtensor sidecar: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Unexpected error fetching node info: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Internal server error: {str(e)}"
            )

    async def startup_event(self) -> None:
        """Initialize background tasks on service startup"""
        asyncio.create_task(self.periodic_rate_limit_updates())
        logger.info("Managing service started with background rate limit updating")

    async def periodic_rate_limit_updates(self) -> None:
        """Background task to periodically update rate limits"""
        while True:
            try:
                logger.debug("Updating validator rate limits")
                await self.rate_limit_manager.update_validator_rate_limits()
                logger.debug("Rate limits updated successfully")
            except Exception as e:
                logger.error(f"Failed to update rate limits: {str(e)}")

            await asyncio.sleep(SETTINGS.substrate_sidecar.sync_node_info_interval)

    async def consume(
        self,
        request: ConsumeRequest,
        rate_limit_manager: RateLimitManager = Depends(get_rate_limit_manager),
        score_manager: ScoreManager = Depends(get_score_manager),
    ) -> Dict[str, Any]:
        """
        Consume rate limit for miners based on the specified strategy.

        If miner_hotkey is provided, attempts to consume quota for the current validator accessing that miner.
        Otherwise, samples miners based on their remaining capacity for this validator.
        """

        if request.miner_hotkey:
            success = await rate_limit_manager.consume_validator_quota(
                validator_hotkey=request.validator_hotkey,
                miner_hotkey=request.miner_hotkey,
                threshold=request.rate_limit_threshold,
            )

            if not success:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded for validator {request.validator_hotkey} accessing miner {request.miner_hotkey}",
                )

            logger.info(
                f"Consumed quota for validator {request.validator_hotkey} accessing miner {request.miner_hotkey}"
            )
            return {"miner_hotkeys": [request.miner_hotkey], "uids": [None]}

        node_infos = await self.fetch_node_infos()
        all_hotkeys = [node.hotkey for node in node_infos.nodes]

        if not all_hotkeys:
            raise HTTPException(
                status_code=404, detail="No miners available in the network"
            )

        top_miners = []
        if request.top_score < 1.0:
            n_top_miners = int(len(all_hotkeys) * request.top_score)
            logger.info(f"Sampling {n_top_miners} top miners")
            scores = await score_manager.get_all_miner_scores()
            scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            top_miners = [hotkey for hotkey, _ in scores[:n_top_miners]]
        else:
            top_miners = all_hotkeys
        logger.info(f"Top miners: {top_miners}")

        remaining_capacities = (
            await rate_limit_manager.get_validators_remaining_capacity(
                validator_hotkey=request.validator_hotkey, miner_hotkeys=top_miners
            )
        )

        total_capacity = sum(remaining_capacities)
        if total_capacity <= 0:
            raise HTTPException(
                status_code=429,
                detail="Validator has reached quota limits for all miners",
            )
        sampling_weights = np.array(remaining_capacities) / total_capacity

        try:
            sampled_indices = np.random.choice(
                len(top_miners),
                size=min(request.sample_size, len(top_miners)),
                replace=False,
                p=sampling_weights,
            )
            sampled_hotkeys = [top_miners[i] for i in sampled_indices]
        except ValueError as e:
            logger.error(f"Sampling error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Failed to sample miners: {str(e)}"
            )

        consumed_hotkeys = []
        for hotkey in sampled_hotkeys:
            success = await rate_limit_manager.consume_validator_quota(
                validator_hotkey=request.validator_hotkey,
                miner_hotkey=hotkey,
                threshold=request.rate_limit_threshold,
            )
            if success:
                consumed_hotkeys.append(hotkey)

        if not consumed_hotkeys:
            raise HTTPException(
                status_code=429,
                detail="Could not consume quota for any of the sampled miners",
            )

        uids = []
        for hotkey in consumed_hotkeys:
            try:
                uid = node_infos.get_uid(hotkey)
                uids.append(uid)
            except ValueError:
                uids.append(None)

        logger.info(
            f"Sampled and consumed quota for validator {request.validator_hotkey} accessing miners: {consumed_hotkeys}"
        )
        return {"miner_hotkeys": consumed_hotkeys, "uids": uids}

    async def update_score(
        self,
        request: UpdateScoreRequest,
        score_manager: ScoreManager = Depends(get_score_manager),
    ) -> Dict[str, Any]:
        """
        Update the score for a miner based on evaluation results.
        Stores historical scoring data for future use.
        """
        try:
            await score_manager.update_miner_score(
                miner_hotkeys=request.miner_hotkeys,
                scores=request.scores,
            )
            return {"success": True, "miner_hotkeys": request.miner_hotkeys}
        except Exception as e:
            logger.error(f"Failed to update score: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Failed to update score: {str(e)}"
            )

    async def get_scores(
        self,
        score_manager: ScoreManager = Depends(get_score_manager),
    ) -> Dict[str, Any]:
        """
        Get the current scores for all miners.
        Returns a dictionary mapping miner hotkeys to their current average scores.
        """
        try:
            scores = await score_manager.get_all_miner_scores()
            return {"scores": scores}
        except Exception as e:
            logger.error(f"Failed to get scores: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Failed to get scores: {str(e)}"
            )

    async def health_check(self) -> Dict[str, str]:
        """Simple health check endpoint"""
        return {"status": "healthy"}


service = ManagingService()
app = service.app
