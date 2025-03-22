from async_substrate_interface import AsyncSubstrateInterface
from services.sidecar_subtensor.schemas import NodeInfo, NodeInfoList
from redis.asyncio import Redis
import json
import asyncio
from loguru import logger
from scalecodec.utils.ss58 import ss58_encode
import netaddr


def _int_to_ip(ip: int) -> str:
    return str(netaddr.IPAddress(ip))


def _ss58_encode(address: list[int] | list[list[int]]) -> str:
    if not isinstance(address[0], int):
        address = address[0]
    return ss58_encode(bytes(address).hex(), 42)


async def sync_node_info_task(
    redis: Redis,
    substrate: AsyncSubstrateInterface,
    netuid: int,
    redis_key: str,
    interval: int = 600,
):
    # Reset redis key
    await redis.delete(redis_key.format(netuid=netuid))

    while True:
        logger.info(f"Syncing node info for netuid {netuid}")

        response = await substrate.runtime_call(
            api="SubnetInfoRuntimeApi",
            method="get_metagraph",
            params=[netuid],
            block_hash=None,
        )
        raw_node_infos = response.value

        node_infos = []

        for uid, hotkey in enumerate(raw_node_infos["hotkeys"]):
            axon = raw_node_infos["axons"][uid]
            alpha_stake = raw_node_infos["alpha_stake"][uid] * 1e-9
            tao_stake = raw_node_infos["tao_stake"][uid] * 1e-9
            stake = raw_node_infos["total_stake"][uid] * 1e-9
            trust = raw_node_infos["trust"][uid]
            last_updated = float(raw_node_infos["last_update"][uid])
            ip = _int_to_ip(axon["ip"])
            ip_type = "IPv4" if axon["ip_type"] == 0 else "IPv6"
            port = axon["port"]
            protocol = "http" if axon["protocol"] == 0 else "https"
            hotkey = _ss58_encode(hotkey)

            node_info = NodeInfo(
                uid=uid,
                hotkey=hotkey,
                alpha_stake=alpha_stake,
                tao_stake=tao_stake,
                stake=stake,
                trust=trust,
                last_updated=last_updated,
                ip=ip,
                ip_type=ip_type,
                port=port,
                protocol=protocol,
            )

            node_infos.append(node_info)

        logger.info(f"Found {len(node_infos)} node infos for netuid {netuid}")

        key = redis_key.format(netuid=netuid)

        await redis.set(
            key,
            NodeInfoList(
                nodes=[node_info.model_dump() for node_info in node_infos]
            ).model_dump_json(),
        )

        logger.info(f"Synced node info for netuid {netuid}")

        await asyncio.sleep(interval)
