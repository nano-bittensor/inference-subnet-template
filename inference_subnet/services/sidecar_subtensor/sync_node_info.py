from async_substrate_interface import AsyncSubstrateInterface
from inference_subnet.services.sidecar_subtensor.schemas import (
    NodeInfo,
    NodeInfoList,
)
from redis.asyncio import Redis
import asyncio
from loguru import logger
from scalecodec.utils.ss58 import ss58_encode
import netaddr
from inference_subnet.settings import SETTINGS


def _int_to_ip_address(ip_int: int) -> str:
    """Convert integer representation of IP to string format."""
    return str(netaddr.IPAddress(ip_int))


def _convert_to_ss58_address(address: list[int] | list[list[int]]) -> str:
    """Convert byte array to SS58 encoded address."""
    if not isinstance(address[0], int):
        address = address[0]
    return ss58_encode(bytes(address).hex(), 42)


async def sync_metagraph_data(
    redis: Redis,
    substrate: AsyncSubstrateInterface,
):
    """Periodically fetch and store subnet metagraph data in Redis."""
    # Reset redis key
    netuid = SETTINGS.substrate_sidecar.netuid
    redis_key = SETTINGS.substrate_sidecar.redis_keys["node_infos"]
    await redis.delete(redis_key.format(netuid=netuid))

    while True:
        logger.info(f"Fetching metagraph data for netuid {netuid}")

        metagraph_data = await substrate.runtime_call(
            api="SubnetInfoRuntimeApi",
            method="get_metagraph",
            params=[netuid],
            block_hash=None,
        )
        raw_metagraph = metagraph_data.value

        node_infos = []

        for uid, hotkey in enumerate(raw_metagraph["hotkeys"]):
            axon_data = raw_metagraph["axons"][uid]

            # Convert values with appropriate scaling
            alpha_stake = raw_metagraph["alpha_stake"][uid] * 1e-9
            tao_stake = raw_metagraph["tao_stake"][uid] * 1e-9
            total_stake = raw_metagraph["total_stake"][uid] * 1e-9
            trust_score = raw_metagraph["trust"][uid]
            last_updated_timestamp = float(raw_metagraph["last_update"][uid])

            # Format network information
            ip_address = _int_to_ip_address(axon_data["ip"])
            ip_type = "IPv4" if axon_data["ip_type"] == 0 else "IPv6"
            port_number = axon_data["port"]
            protocol_type = "http" if axon_data["protocol"] == 0 else "https"
            ss58_address = _convert_to_ss58_address(hotkey)

            node_info = NodeInfo(
                uid=uid,
                hotkey=ss58_address,
                alpha_stake=alpha_stake,
                tao_stake=tao_stake,
                stake=total_stake,
                trust=trust_score,
                last_updated=last_updated_timestamp,
                ip=ip_address,
                ip_type=ip_type,
                port=port_number,
                protocol=protocol_type,
            )

            node_infos.append(node_info)

        logger.info(f"Found {len(node_infos)} validators for netuid {netuid}")

        redis_cache_key = redis_key.format(netuid=netuid)

        await redis.set(
            redis_cache_key,
            NodeInfoList(
                nodes=[node_info.model_dump() for node_info in node_infos]
            ).model_dump_json(),
        )

        logger.info(f"Updated metagraph data in Redis for netuid {netuid}")

        await asyncio.sleep(SETTINGS.substrate_sidecar.sync_node_info_interval)
