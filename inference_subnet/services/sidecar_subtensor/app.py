from async_substrate_interface import AsyncSubstrateInterface
from substrateinterface import Keypair
from inference_subnet.settings import SETTINGS
from fastapi import FastAPI
from redis.asyncio import Redis
from inference_subnet.services.sidecar_subtensor.sync_node_info import (
    sync_metagraph_data,
)
import asyncio
from inference_subnet.services.sidecar_subtensor.schemas import NodeInfoList
import json

app = FastAPI()

KEYPAIR = Keypair.create_from_seed(
    json.load(open(SETTINGS.wallet.wallet_file))["secretSeed"]
)
REDIS = Redis(host=SETTINGS.redis.host, port=SETTINGS.redis.port, db=SETTINGS.redis.db)
SUBSTRATE = AsyncSubstrateInterface(url=SETTINGS.substrate_sidecar.entrypoint)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(
        sync_metagraph_data(
            REDIS,
            SUBSTRATE,
        )
    )


@app.get("/api/nodes")
async def get_nodes():
    """Retrieve the current list of validator nodes in the metagraph."""
    redis_key = SETTINGS.substrate_sidecar.redis_keys["node_infos"].format(
        netuid=SETTINGS.substrate_sidecar.netuid
    )
    cached_node_info = await REDIS.get(redis_key)
    return NodeInfoList.model_validate_json(cached_node_info)


@app.get("/api/status")
async def get_node_status():
    """Return basic information about this node."""
    metagraph_nodes = await get_nodes()
    node_uid = metagraph_nodes.get_uid(KEYPAIR.ss58_address)
    return {
        "ss58_address": KEYPAIR.ss58_address,
        "uid": node_uid,
    }
