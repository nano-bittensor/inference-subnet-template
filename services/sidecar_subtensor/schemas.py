from pydantic import BaseModel


class NodeInfo(BaseModel):
    ip: str
    ip_type: str
    port: int
    protocol: str
    uid: int
    hotkey: str
    alpha_stake: float
    tao_stake: float
    stake: float
    trust: float
    last_updated: float


class NodeInfoList(BaseModel):
    nodes: list[NodeInfo]
