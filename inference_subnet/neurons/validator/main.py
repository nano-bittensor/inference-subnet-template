from httpx import AsyncClient
from redis.asyncio import Redis
from inference_subnet.settings import SETTINGS
from inference_subnet.services.sidecar_subtensor.schemas import NodeInfoList
from inference_subnet.services.managing.schemas import MinerSamplingResponse
from inference_subnet.services.scoring.schemas import ScoreResponse
from inference_subnet.verification import create_headers
import time
import json
import asyncio
from loguru import logger
from substrateinterface import Keypair
from asyncio import Semaphore


class ValidatorNeuron:
    def __init__(self):
        self.redis = Redis(
            host=SETTINGS.redis.host,
            port=SETTINGS.redis.port,
            db=SETTINGS.redis.db,
        )
        self.sidecar_subtensor_client = AsyncClient(
            base_url=SETTINGS.substrate_sidecar.base_url
        )

        wallet_data = json.load(open(SETTINGS.wallet.wallet_file))
        self.keypair = Keypair.create_from_seed(wallet_data["secretSeed"])
        self.validator_hotkey = self.keypair.ss58_address

        self.managing_client = AsyncClient(base_url=SETTINGS.managing.base_url)
        self.synthesizing_client = AsyncClient(base_url=SETTINGS.synthesizing.base_url)
        self.scoring_client = AsyncClient(base_url=SETTINGS.scoring.base_url)

        self._node_infos_cache = None
        self._node_infos_timestamp = 0
        self._cache_ttl = 600

        self.scoring_semaphore = Semaphore(SETTINGS.validating.scoring_semaphore_size)

        self.MAX_SCORES_PER_PERIOD = SETTINGS.validating.max_scores_per_period
        self.SCORE_PERIOD_SECONDS = SETTINGS.validating.score_period_seconds
        self.SCORE_TRACKING_KEY_PREFIX = SETTINGS.validating.score_tracking_key_prefix

    async def fetch_node_infos(self) -> NodeInfoList:
        """Fetch node information from the sidecar service with caching"""
        current_time = time.time()

        if (
            self._node_infos_cache is not None
            and (current_time - self._node_infos_timestamp) < self._cache_ttl
        ):
            logger.debug("Using cached node_infos")
            return self._node_infos_cache

        async with AsyncClient(
            base_url=SETTINGS.substrate_sidecar.base_url,
            timeout=SETTINGS.substrate_sidecar.request_timeout,
        ) as client:
            response = await client.get("/api/nodes")
            if response.status_code != 200:
                logger.error(f"Failed to fetch node info: {response.text}")
                raise Exception(f"Failed to fetch node info: {response.text}")

            self._node_infos_cache = NodeInfoList.model_validate_json(response.text)
            self._node_infos_timestamp = current_time
            logger.debug("Node info cache updated")

            return self._node_infos_cache

    async def _get_challenge_payload(self):
        """Get challenge and payload for validation"""
        challenge_name, payload_model, response_model, api_route = (
            SETTINGS.protocol.sample_challenge
        )

        async with AsyncClient(
            base_url=SETTINGS.synthesizing.base_url,
            timeout=SETTINGS.synthesizing.request_timeout,
        ) as client:
            response = await client.post(
                "/api/get-payload",
                json={"challenge": challenge_name},
            )
            payload = payload_model.model_validate_json(response.text)

        return challenge_name, payload, response_model, api_route

    async def _get_miner_batch(self):
        """Get a batch of miners to validate"""
        async with AsyncClient(
            base_url=SETTINGS.managing.base_url,
            timeout=SETTINGS.managing.request_timeout,
        ) as client:
            response = await client.post(
                "/api/consume",
                json={
                    "validator_hotkey": self.validator_hotkey,
                    "miner_hotkey": "",
                    "rate_limit_threshold": SETTINGS.validating.synthetic_rate_limit_threshold,
                    "sample_size": SETTINGS.validating.batch_size,
                    "top_score": 1.0,
                },
            )
            batch_info = MinerSamplingResponse.model_validate_json(response.text)

        return batch_info

    async def _call_miner_forward(
        self, axon, payload, response_model, api_route, miner_hotkey
    ):
        """Call a miner's forward endpoint with the payload"""
        endpoint = f"http://{axon['ip']}:{axon['port']}{api_route}"
        headers = create_headers(self.keypair, miner_hotkey)
        async with AsyncClient(
            base_url=endpoint,
            timeout=SETTINGS.protocol.timeout,
        ) as client:
            response = await client.post(
                "/api/forward",
                json=payload.model_dump(),
                headers=headers,
            )
            if response.status_code != 200:
                logger.error(f"Failed to call forward: {response.text}")
                return None

            try:
                result = response_model.model_validate_json(response.text)
                return result
            except Exception as e:
                logger.error(f"Failed to validate response: {response.text}")
                return None

    async def _check_and_update_score_count(self, hotkey):
        """
        Check if a hotkey has been scored too many times in the time period.
        Returns True if the hotkey can be scored, False if it should be dropped.
        """
        now = int(time.time())
        tracking_key = f"{self.SCORE_TRACKING_KEY_PREFIX}{hotkey}"

        score_timestamps = await self.redis.zrange(tracking_key, 0, -1, withscores=True)

        cutoff_time = now - self.SCORE_PERIOD_SECONDS
        recent_scores = [ts for _, ts in score_timestamps if ts > cutoff_time]

        if len(recent_scores) >= self.MAX_SCORES_PER_PERIOD:
            return False

        await self.redis.zadd(tracking_key, {hotkey: now})
        await self.redis.expire(tracking_key, self.SCORE_PERIOD_SECONDS * 2)

        await self.redis.zremrangebyscore(tracking_key, 0, cutoff_time)

        return True

    async def _update_scores(self, hotkeys, scores):
        """Update scores for a list of miners"""
        if not hotkeys:
            return

        async with AsyncClient(
            base_url=SETTINGS.managing.base_url,
            timeout=SETTINGS.managing.request_timeout,
        ) as client:
            await client.post(
                "/api/update-score",
                json={"miner_hotkeys": hotkeys, "scores": scores},
            )

    async def validate_batch(self):
        """Validate a batch of miners"""
        challenge_name, payload, response_model, api_route = (
            await self._get_challenge_payload()
        )
        logger.info(f"Challenge: {challenge_name}, Route: {api_route}")
        batch_info = await self._get_miner_batch()

        miner_hotkeys = batch_info.miner_hotkeys
        axons = batch_info.axons

        call_futures = [
            self._call_miner_forward(
                axon, payload, response_model, api_route, miner_hotkey
            )
            for axon, miner_hotkey in zip(axons, miner_hotkeys)
        ]
        results = await asyncio.gather(*call_futures)

        valid_hotkeys = []
        valid_results = []
        invalid_hotkeys = []

        for result, hotkey in zip(results, miner_hotkeys):
            if result is not None:
                valid_hotkeys.append(hotkey)
                valid_results.append(result)
            else:
                invalid_hotkeys.append(hotkey)

        if invalid_hotkeys:
            logger.info(
                f"Updating scores for {len(invalid_hotkeys)} invalid hotkeys: {invalid_hotkeys}"
            )
            await self._update_scores(invalid_hotkeys, [0] * len(invalid_hotkeys))

        if valid_hotkeys:
            filtered_hotkeys = []
            filtered_results = []
            dropout_hotkeys = []

            for hotkey, result in zip(valid_hotkeys, valid_results):
                can_score = await self._check_and_update_score_count(hotkey)
                if can_score:
                    filtered_hotkeys.append(hotkey)
                    filtered_results.append(result)
                else:
                    dropout_hotkeys.append(hotkey)

            if dropout_hotkeys:
                logger.info(
                    f"Dropping {len(dropout_hotkeys)} hotkeys due to scoring rate limits"
                )

            if filtered_hotkeys:
                async with self.scoring_semaphore:
                    async with AsyncClient(
                        base_url=SETTINGS.scoring.base_url,
                        timeout=SETTINGS.scoring.request_timeout,
                    ) as client:
                        response = await client.post(
                            "/api/score",
                            json={
                                "miner_responses": filtered_results,
                                "base_payload": payload.model_dump(),
                            },
                        )
                        scores = ScoreResponse.model_validate_json(response.text)

                await self._update_scores(filtered_hotkeys, scores)
