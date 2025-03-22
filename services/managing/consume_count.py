from redis.asyncio import Redis
from settings import SETTINGS


async def consume_rate_limit(
    redis: Redis,
    miner_hotkey: str,
    validator_hotkey: str,
    netuid: int,
) -> bool:
    current_epoch = SETTINGS.query.get_current_epoch()
    key = SETTINGS.query.redis_keys["rate_limit_consumed"].format(
        netuid=netuid,
        epoch=current_epoch,
        miner_hotkey=miner_hotkey,
        validator_hotkey=validator_hotkey,
    )
    count = await redis.get(key)
    max_count = await redis.get(SETTINGS.query.redis_keys["rate_limit_distribution"])
    if count is None:
        await redis.set(key, 1)
        count = 1

    if count >= max_count:
        return False

    await redis.incrby(key, 1)

    return True


async def get_rate_limit_consumed(
    redis: Redis,
    redis_key: str,
) -> int:
    count = await redis.get(redis_key)
    if count is None:
        return 0
    return int(count)
