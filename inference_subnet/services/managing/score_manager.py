from redis.asyncio import Redis
import json
from loguru import logger
from typing import Dict, List, Any
import time

from inference_subnet.settings import SETTINGS


class ScoreManager:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def update_miner_score(
        self,
        miner_hotkeys: List[str],
        scores: List[float] | None = None,
    ) -> None:
        """
        Update the score for a specific miner.

        Args:
            miner_hotkeys: List of miner's public keys
            scores: The new score values (typically 0.0 to 1.0)
        """
        current_time = time.time()
        max_history = SETTINGS.managing.n_historical_scores

        # Prepare pipeline for batch operations
        async with self.redis.pipeline() as pipe:
            # First, get all existing score histories
            history_keys = [
                SETTINGS.managing.redis_keys["scores_history"].format(
                    miner_hotkey=hotkey
                )
                for hotkey in miner_hotkeys
            ]
            await pipe.mget(history_keys)
            existing_scores_json_list = await pipe.execute()

            # Process each miner's scores and prepare updates
            for i, (miner_hotkey, score, existing_scores_json) in enumerate(
                zip(miner_hotkeys, scores, existing_scores_json_list[0])
            ):
                # Process score history
                if existing_scores_json:
                    scores_history = json.loads(existing_scores_json)
                else:
                    scores_history = []

                # Add new score with timestamp
                score_entry = {"score": score, "timestamp": current_time}
                scores_history.append(score_entry)

                # Keep only the most recent N scores
                if len(scores_history) > max_history:
                    scores_history = scores_history[-max_history:]

                # Calculate average score
                avg_score = (
                    sum(entry["score"] for entry in scores_history)
                    / SETTINGS.managing.n_historical_scores
                )

                # Add commands to pipeline
                history_key = SETTINGS.managing.redis_keys["scores_history"].format(
                    miner_hotkey=miner_hotkey
                )
                avg_key = SETTINGS.managing.redis_keys["scores_average"].format(
                    miner_hotkey=miner_hotkey
                )

                # Set history and expiration
                await pipe.set(history_key, json.dumps(scores_history))
                await pipe.expire(
                    history_key,
                    SETTINGS.managing.epoch_interval
                    * max_history
                    * SETTINGS.managing.score_history_ttl_factor,
                )

                # Set average score
                await pipe.set(avg_key, avg_score)

                logger.debug(
                    f"Prepared score update for {miner_hotkey}: {score} (avg: {avg_score:.4f})"
                )

            # Execute all commands in a single batch
            await pipe.execute()

    async def get_miner_average_score(
        self,
        miner_hotkey: str,
    ) -> float:
        """
        Get the average score for a specific miner.

        Args:
            miner_hotkey: Miner's public key

        Returns:
            Average score (0.0 to 1.0)
        """
        avg_key = SETTINGS.managing.redis_keys["scores_average"].format(
            miner_hotkey=miner_hotkey
        )
        avg_score = await self.redis.get(avg_key)

        if avg_score is None:
            # No score recorded, return default
            return 0.5

        return float(avg_score)

    async def get_miner_score_history(
        self,
        miner_hotkey: str,
    ) -> List[Dict[str, Any]]:
        """
        Get the score history for a specific miner.

        Args:
            miner_hotkey: Miner's public key

        Returns:
            List of score history entries with score and timestamp
        """
        history_key = SETTINGS.managing.redis_keys["scores_history"].format(
            miner_hotkey=miner_hotkey
        )
        history_json = await self.redis.get(history_key)

        if not history_json:
            return []

        return json.loads(history_json)

    async def get_all_miner_scores(
        self,
    ) -> Dict[str, float]:
        """
        Get average scores for all miners.

        Returns:
            Dictionary mapping miner hotkeys to their average scores
        """
        # Get all average score keys
        key_pattern = SETTINGS.managing.redis_keys["scores_average"].format(
            miner_hotkey="*"
        )
        keys = await self.redis.keys(key_pattern)

        if not keys:
            return {}

        # Get all scores in one operation
        values = await self.redis.mget(keys)

        # Create mapping from hotkey to score
        scores = {}
        for i, key in enumerate(keys):
            hotkey = key.split(":")[-1]
            scores[hotkey] = float(values[i] or 0.5)

        return scores
