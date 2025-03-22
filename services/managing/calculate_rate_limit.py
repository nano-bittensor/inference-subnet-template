import json
from httpx import AsyncClient
from redis.asyncio import Redis
from services.sidecar_subtensor.schemas import NodeInfoList


async def allocate_rate_limit(
    redis: Redis,
    redis_key: str,
    sidecar_subtensor_client: AsyncClient,
    min_stake: int,
    max_rate_limit: int,
) -> None:
    response = await sidecar_subtensor_client.get("/api/node_info")
    node_infos = NodeInfoList.model_validate_json(response.text)
    hotkeys_stakes = {
        node_info.hotkey: node_info.stake
        for node_info in node_infos
        if node_info.stake >= min_stake
    }

    total_stake = sum(hotkeys_stakes.values())

    normalized_hotkeys_stakes = {
        hotkey: stake / total_stake for hotkey, stake in hotkeys_stakes.items()
    }

    rate_limits = {
        hotkey: max_rate_limit * stake
        for hotkey, stake in normalized_hotkeys_stakes.items()
    }

    await redis.set(redis_key, json.dumps(rate_limits))


async def get_rate_limit(
    redis: Redis,
    redis_key: str,
) -> int:
    rate_limit = await redis.get(redis_key)
    if rate_limit is None:
        return 0
    return int(rate_limit)
