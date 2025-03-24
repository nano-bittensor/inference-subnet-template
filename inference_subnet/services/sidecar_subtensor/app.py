from async_substrate_interface import AsyncSubstrateInterface
from substrateinterface import Keypair
from inference_subnet.settings import SETTINGS
from fastapi import FastAPI, Depends, HTTPException
from redis.asyncio import Redis
import asyncio
from inference_subnet.services.sidecar_subtensor.schemas import NodeInfoList, NodeInfo
import json
from loguru import logger
import netaddr
from scalecodec.utils.ss58 import ss58_encode
from typing import List, Dict, Any


class SidecarSubtensorService:
    def __init__(self):
        self.app = FastAPI(title="Inference Subnet Sidecar Subtensor Service")
        self.redis = Redis(
            host=SETTINGS.redis.host,
            port=SETTINGS.redis.port,
            db=SETTINGS.redis.db,
            decode_responses=True,
        )
        self.keypair = Keypair.create_from_seed(
            json.load(open(SETTINGS.wallet.wallet_file))["secretSeed"]
        )
        self.substrate = AsyncSubstrateInterface(
            url=SETTINGS.substrate_sidecar.entrypoint
        )
        self.setup_routes()
        self.setup_events()

    def setup_routes(self):
        self.app.add_api_route(
            "/api/nodes",
            self.get_nodes,
            methods=["GET"],
            response_model=NodeInfoList,
            status_code=200,
            tags=["nodes"],
            description="Get the current list of validator nodes in the metagraph.",
        )
        self.app.add_api_route(
            "/api/status",
            self.get_node_status,
            methods=["GET"],
            status_code=200,
            tags=["status"],
            description="Get basic information about this node.",
        )
        self.app.add_api_route(
            "/api/health",
            self.health_check,
            methods=["GET"],
            status_code=200,
            tags=["health"],
            description="Simple health check endpoint",
        )

    def setup_events(self):
        self.app.on_event("startup")(self.startup_event)

    async def get_redis(self) -> Redis:
        """Dependency to get Redis connection"""
        return self.redis

    async def get_substrate(self) -> AsyncSubstrateInterface:
        """Dependency to get substrate connection"""
        return self.substrate

    async def startup_event(self):
        """Initialize background tasks on service startup"""
        asyncio.create_task(self.sync_metagraph_data())
        logger.info(
            "Sidecar subtensor service started with background metagraph syncing"
        )

    async def sync_metagraph_data(self):
        """Periodically fetch and store subnet metagraph data in Redis."""
        # Reset redis key
        netuid = SETTINGS.substrate_sidecar.netuid
        redis_key = SETTINGS.substrate_sidecar.redis_keys["node_infos"]
        await self.redis.delete(redis_key.format(netuid=netuid))

        while True:
            logger.info(f"Fetching metagraph data for netuid {netuid}")

            try:
                metagraph_data = await self.substrate.runtime_call(
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
                    ip_address = self._int_to_ip_address(axon_data["ip"])
                    ip_type = "IPv4" if axon_data["ip_type"] == 0 else "IPv6"
                    port_number = axon_data["port"]
                    protocol_type = "http" if axon_data["protocol"] == 0 else "https"
                    ss58_address = self._convert_to_ss58_address(hotkey)

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

                await self.redis.set(
                    redis_cache_key,
                    NodeInfoList(
                        nodes=[node_info.model_dump() for node_info in node_infos]
                    ).model_dump_json(),
                )

                logger.info(f"Updated metagraph data in Redis for netuid {netuid}")

            except Exception as e:
                logger.error(f"Error syncing metagraph data: {str(e)}")

            await asyncio.sleep(SETTINGS.substrate_sidecar.sync_node_info_interval)

    def _int_to_ip_address(self, ip_int: int) -> str:
        """Convert integer representation of IP to string format."""
        return str(netaddr.IPAddress(ip_int))

    def _convert_to_ss58_address(self, address: List[int] | List[List[int]]) -> str:
        """Convert byte array to SS58 encoded address."""
        if not isinstance(address[0], int):
            address = address[0]
        return ss58_encode(bytes(address).hex(), 42)

    async def get_nodes(self) -> NodeInfoList:
        """Retrieve the current list of validator nodes in the metagraph."""
        redis_key = SETTINGS.substrate_sidecar.redis_keys["node_infos"].format(
            netuid=SETTINGS.substrate_sidecar.netuid
        )
        cached_node_info = await self.redis.get(redis_key)

        if not cached_node_info:
            raise HTTPException(
                status_code=503,
                detail="Node information not available yet. Please try again later.",
            )

        return NodeInfoList.model_validate_json(cached_node_info)

    async def get_node_status(self) -> Dict[str, Any]:
        """Return basic information about this node."""
        try:
            metagraph_nodes = await self.get_nodes()
            node_uid = metagraph_nodes.get_uid(self.keypair.ss58_address)
            return {
                "ss58_address": self.keypair.ss58_address,
                "uid": node_uid,
                "status": "registered" if node_uid is not None else "unregistered",
            }
        except HTTPException as e:
            return {
                "ss58_address": self.keypair.ss58_address,
                "status": "error",
                "error": e.detail,
            }
        except Exception as e:
            logger.error(f"Error getting node status: {str(e)}")
            return {
                "ss58_address": self.keypair.ss58_address,
                "status": "error",
                "error": str(e),
            }

    async def health_check(self) -> Dict[str, str]:
        """Simple health check endpoint"""
        return {"status": "healthy"}


service = SidecarSubtensorService()
app = service.app
