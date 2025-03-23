from redis.asyncio import Redis
from httpx import AsyncClient
import json
from loguru import logger
from typing import List, Dict, Any
import time

from inference_subnet.settings import SETTINGS


class RateLimitManager:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def update_validator_rate_limits(self) -> None:
        """
        Update rate limits for validators to use when accessing miners.
        """
        try:
            # Fetch node info from sidecar service
            async with AsyncClient(
                base_url=SETTINGS.substrate_sidecar.base_url
            ) as client:
                response = await client.get("/api/nodes")
                response.raise_for_status()
                node_data = response.json()

            # Extract stake information
            nodes = node_data.get("nodes", [])

            # Filter nodes with minimum stake
            eligible_nodes = [
                node
                for node in nodes
                if node.get("stake", 0) >= SETTINGS.managing.rate_limit_min_stake
            ]

            if not eligible_nodes:
                logger.warning("No eligible nodes found with sufficient stake")
                return

            # Calculate total stake
            total_stake = sum(node.get("stake", 0) for node in eligible_nodes)

            # Distribute rate limits proportionally to stake
            rate_limits = {}
            for node in eligible_nodes:
                hotkey = node.get("hotkey")
                stake = node.get("stake", 0)
                rate_limit = int(
                    SETTINGS.managing.rate_limit_max_requests * (stake / total_stake)
                )
                rate_limits[hotkey] = max(1, rate_limit)  # Ensure minimum of 1
            logger.info(f"Rate limits: {rate_limits}")
            # Store in Redis
            redis_key = "rate_limits:validators"
            await self.redis.set(redis_key, json.dumps(rate_limits))
            await self.redis.expire(redis_key, SETTINGS.managing.epoch_interval * 2)

            logger.info(f"Updated validator rate limits for {len(rate_limits)} nodes")
        except Exception as e:
            logger.error(f"Failed to update validator rate limits: {str(e)}")
            raise

    async def get_validator_quota_for_miner(self, validator_hotkey: str) -> int:
        """
        Get the maximum query quota for a specific validator.

        Args:
            validator_hotkey: Validator's public key

        Returns:
            The rate limit value (max requests per epoch)
        """
        try:
            # Get validator rate limits
            redis_key = "rate_limits:validators"
            rate_limits_json = await self.redis.get(redis_key)

            if not rate_limits_json:
                logger.warning("No validator rate limits found, triggering update")
                await self.update_validator_rate_limits()
                rate_limits_json = await self.redis.get(redis_key)

                if not rate_limits_json:
                    logger.error(
                        "Failed to get validator rate limits even after update"
                    )
                    return (
                        SETTINGS.managing.rate_limit_max_requests // 100
                    )  # Default to a small value

            rate_limits = json.loads(rate_limits_json)
            return int(rate_limits.get(validator_hotkey, 0))
        except Exception as e:
            logger.error(f"Error getting validator quota: {str(e)}")
            return 0

    async def get_validator_consumed_quota(
        self, validator_hotkey: str, miner_hotkey: str
    ) -> int:
        """
        Get the current consumption for a validator accessing a specific miner in the current epoch.

        Args:
            validator_hotkey: Validator's public key
            miner_hotkey: Miner's public key

        Returns:
            Number of requests consumed in the current epoch
        """
        current_epoch = int(time.time() // SETTINGS.managing.epoch_interval)
        redis_key = (
            f"rate_limits:consumed:{current_epoch}:{validator_hotkey}:{miner_hotkey}"
        )

        consumed = await self.redis.get(redis_key)
        return int(consumed or 0)

    async def consume_validator_quota(
        self, validator_hotkey: str, miner_hotkey: str, threshold: float = 1.0
    ) -> bool:
        """
        Attempt to consume quota for a validator accessing a miner.

        Args:
            validator_hotkey: Validator's public key
            miner_hotkey: Miner's public key
            threshold: Fraction of max quota that can be consumed (0.0 to 1.0)

        Returns:
            True if quota was successfully consumed, False otherwise
        """
        current_epoch = int(time.time() // SETTINGS.managing.epoch_interval)
        consumed_key = (
            f"rate_limits:consumed:{current_epoch}:{validator_hotkey}:{miner_hotkey}"
        )

        # Get max quota for this validator
        max_quota = await self.get_validator_quota_for_miner(validator_hotkey)

        if max_quota <= 0:
            logger.warning(f"Validator {validator_hotkey} has no quota allocation")
            return False

        # Calculate threshold quota
        threshold_quota = int(max_quota * threshold)

        # Use WATCH/MULTI/EXEC pattern for optimistic locking
        try:
            await self.redis.watch(consumed_key)

            # Get current consumption
            current_consumption = int(await self.redis.get(consumed_key) or 0)

            # Check if consumption exceeds threshold BEFORE incrementing
            if current_consumption >= threshold_quota:
                logger.debug(
                    f"Quota exceeded for validator {validator_hotkey} accessing miner {miner_hotkey}: {current_consumption}/{threshold_quota}"
                )
                await self.redis.unwatch()
                return False

            # Begin transaction
            tr = self.redis.pipeline()
            tr.incr(consumed_key)
            tr.expire(consumed_key, SETTINGS.managing.epoch_interval * 2)
            await tr.execute()

            logger.debug(
                f"Quota consumed for validator {validator_hotkey} accessing miner {miner_hotkey}: {current_consumption+1}/{threshold_quota}"
            )
            return True
        except Exception as e:
            logger.error(f"Error consuming quota: {str(e)}")
            return False
        finally:
            # Ensure we unwatch in case of errors
            try:
                await self.redis.unwatch()
            except:
                pass

    async def get_validators_remaining_capacity(
        self, validator_hotkey: str, miner_hotkeys: List[str]
    ) -> List[int]:
        """
        Get remaining capacity for a validator to access multiple miners.

        Args:
            validator_hotkey: Validator's public key
            miner_hotkeys: List of miner public keys

        Returns:
            List of remaining quota capacity for each miner
        """
        # Get validator's quota
        max_quota = await self.get_validator_quota_for_miner(validator_hotkey)

        if max_quota <= 0:
            logger.warning(f"Validator {validator_hotkey} has no quota allocation")
            return [1 for _ in miner_hotkeys]  # Default equal weights

        current_epoch = int(time.time() // SETTINGS.managing.epoch_interval)

        # Prepare keys for all miners
        consumed_keys = [
            f"rate_limits:consumed:{current_epoch}:{validator_hotkey}:{hotkey}"
            for hotkey in miner_hotkeys
        ]

        # Get consumed values in a single operation
        consumed_values = await self.redis.mget(consumed_keys)

        # Calculate remaining capacity
        remaining_capacity = []
        for i, hotkey in enumerate(miner_hotkeys):
            consumed = int(consumed_values[i] or 0)
            remaining = max(0, max_quota - consumed)
            remaining_capacity.append(
                remaining or 1
            )  # Ensure minimum of 1 for sampling

        return remaining_capacity
