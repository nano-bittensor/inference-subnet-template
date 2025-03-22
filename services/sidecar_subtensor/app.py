from async_substrate_interface import AsyncSubstrateInterface
from settings import SETTINGS
from fastapi import FastAPI
from redis.asyncio import Redis
from services.sidecar_subtensor.sync_node_info import sync_node_info_task
import asyncio
from services.sidecar_subtensor.schemas import NodeInfoList

app = FastAPI()

REDIS = Redis(host=SETTINGS.redis.host, port=SETTINGS.redis.port, db=SETTINGS.redis.db)
SUBSTRATE = AsyncSubstrateInterface(url=SETTINGS.substrate_sidecar.entrypoint)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(
        sync_node_info_task(
            REDIS,
            SUBSTRATE,
            SETTINGS.substrate_sidecar.netuid,
            SETTINGS.substrate_sidecar.redis_keys["node_infos"],
            SETTINGS.substrate_sidecar.sync_node_info_interval,
        )
    )


@app.get("/api/node_info")
async def get_node_info():
    key = SETTINGS.substrate_sidecar.redis_keys["node_infos"].format(
        netuid=SETTINGS.substrate_sidecar.netuid
    )
    node_info = await REDIS.get(key)
    return NodeInfoList.model_validate_json(node_info)
