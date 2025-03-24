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
        self.app.add_api_route(
            "/api/consume",
            self.consume,
            methods=["POST"],
            response_model=MinerSamplingResponse,
            status_code=200,
            tags=["consumption"],
            description="Handle miner consumption rate limits and sampling",
        )
        self.app.add_api_route(
            "/api/update-score",
            self.update_score,
            methods=["POST"],
            status_code=200,
            tags=["scoring"],
            description="Update miner scores based on performance evaluations",
        )
        self.app.add_api_route(
            "/api/get-scores",
            self.get_scores,
            methods=["GET"],
            response_model=ScoreResponse,
            status_code=200,
            tags=["scoring"],
            description="Retrieve current scores for all miners",
        )
        self.app.add_api_route(
            "/api/health",
            self.health_check,
            methods=["GET"],
            status_code=200,
            tags=["health"],
            description="Service health check endpoint",
        )

    def setup_events(self):
        self.app.on_event("startup")(self.startup_event)

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
    ) -> Dict[str, Any]:
        """
        Consume rate limit for miners based on the specified strategy.
        Coordinates consumption workflow through sub-functions.
        """
        try:
            if request.miner_hotkey:
                return await self._handle_single_miner_consumption(request)

            node_infos = await self.fetch_node_infos()
            all_hotkeys = self._get_valid_miner_hotkeys(node_infos)
            top_miners = await self._select_top_miners(all_hotkeys, request.top_score)

            sampling_weights = await self._calculate_sampling_weights(
                request.validator_hotkey, top_miners
            )
            sampled_hotkeys = self._sample_miners(
                top_miners, sampling_weights, request.sample_size
            )
            consumed_hotkeys = await self._consume_quotas_for_miners(
                request.validator_hotkey, sampled_hotkeys, request.rate_limit_threshold
            )

            metadata = self._get_metadata_for_hotkeys(node_infos, consumed_hotkeys)
            self._log_consumption_success(request.validator_hotkey, consumed_hotkeys)

            return {"miner_hotkeys": consumed_hotkeys, **metadata}
        except Exception as e:
            logger.error(f"Failed to consume: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to consume: {str(e)}")

    async def _handle_single_miner_consumption(
        self, request: ConsumeRequest
    ) -> Dict[str, Any]:
        """Handle consumption for explicit miner hotkey case"""
        success = await self.rate_limit_manager.consume_validator_quota(
            validator_hotkey=request.validator_hotkey,
            miner_hotkey=request.miner_hotkey,
            threshold=request.rate_limit_threshold,
        )
        node_infos = await self.fetch_node_infos()
        metadata = self._get_metadata_for_hotkeys(node_infos, [request.miner_hotkey])
        if not success:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded for validator {request.validator_hotkey} accessing miner {request.miner_hotkey}",
            )
        return {"miner_hotkeys": [request.miner_hotkey], **metadata}

    def _get_valid_miner_hotkeys(self, node_infos: NodeInfoList) -> list[str]:
        """Validate and extract miner hotkeys from node info"""
        if not node_infos.nodes:
            raise HTTPException(
                status_code=404, detail="No miners available in the network"
            )

        all_hotkeys = [node.hotkey for node in node_infos.nodes]
        if not all_hotkeys:
            raise HTTPException(
                status_code=404, detail="No miners available in the network"
            )
        return all_hotkeys

    async def _select_top_miners(
        self, all_hotkeys: list[str], top_score: float
    ) -> list[str]:
        """Select top miners based on scoring threshold"""
        if top_score >= 1.0:
            return all_hotkeys

        n_top_miners = int(len(all_hotkeys) * top_score)
        logger.info(f"Sampling {n_top_miners} top miners")
        scores = await self.score_manager.get_all_miner_scores()
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [hotkey for hotkey, _ in sorted_scores[:n_top_miners]]

    async def _calculate_sampling_weights(
        self, validator_hotkey: str, top_miners: list[str]
    ) -> np.ndarray:
        """Calculate weighted sampling distribution based on remaining capacities"""
        remaining_capacities = (
            await self.rate_limit_manager.get_validators_remaining_capacity(
                validator_hotkey=validator_hotkey, miner_hotkeys=top_miners
            )
        )
        total_capacity = sum(remaining_capacities)
        if total_capacity <= 0:
            raise HTTPException(
                status_code=429,
                detail="Validator has reached quota limits for all miners",
            )
        return np.array(remaining_capacities) / total_capacity

    def _sample_miners(
        self, top_miners: list[str], sampling_weights: np.ndarray, sample_size: int
    ) -> list[str]:
        """Perform weighted random sampling of miners"""
        try:
            sampled_indices = np.random.choice(
                len(top_miners),
                size=min(sample_size, len(top_miners)),
                replace=False,
                p=sampling_weights,
            )
            return [top_miners[i] for i in sampled_indices]
        except ValueError as e:
            logger.error(f"Sampling error: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Failed to sample miners: {str(e)}"
            )

    async def _consume_quotas_for_miners(
        self, validator_hotkey: str, miner_hotkeys: list[str], threshold: float
    ) -> list[str]:
        """Attempt quota consumption for sampled miners"""
        consumed = []
        for hotkey in miner_hotkeys:
            success = await self.rate_limit_manager.consume_validator_quota(
                validator_hotkey=validator_hotkey,
                miner_hotkey=hotkey,
                threshold=threshold,
            )
            if success:
                consumed.append(hotkey)
        if not consumed:
            raise HTTPException(
                status_code=429,
                detail="Could not consume quota for any of the sampled miners",
            )
        return consumed

    def _get_metadata_for_hotkeys(
        self, node_infos: NodeInfoList, hotkeys: list[str]
    ) -> list[int]:
        """Map miner hotkeys to their UIDs"""
        metadata = {
            "uids": [],
            "axons": [],
        }
        for hotkey in hotkeys:
            try:
                metadata["uids"].append(node_infos.get_uid(hotkey))
            except ValueError:
                metadata["uids"].append(None)
            try:
                metadata["axons"].append(node_infos.get_axon(hotkey))
            except ValueError:
                metadata["axons"].append(None)
        return metadata

    def _log_consumption_success(
        self, validator_hotkey: str, consumed_hotkeys: list[str]
    ) -> None:
        """Log successful consumption events"""
        logger.info(
            f"Sampled and consumed quota for validator {validator_hotkey} "
            f"accessing miners: {consumed_hotkeys}"
        )

    async def update_score(
        self,
        request: UpdateScoreRequest,
    ) -> Dict[str, Any]:
        """
        Update the score for a miner based on evaluation results.
        Simplified with direct manager access.
        """
        try:
            await self.score_manager.update_miner_score(
                miner_hotkeys=request.miner_hotkeys,
                scores=request.scores,
            )
            return {"success": True, "miner_hotkeys": request.miner_hotkeys}
        except Exception as e:
            logger.error(f"Failed to update score: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Failed to update score: {str(e)}"
            )

    async def get_scores(self) -> Dict[str, Any]:
        """
        Get the current scores for all miners.
        Simplified with direct manager access.
        """
        try:
            scores = await self.score_manager.get_all_miner_scores()
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
