from pydantic import BaseModel


class NodeInfo(BaseModel):
    """Information about a validator node in the subnet."""

    ip: str
    ip_type: str
    port: int
    protocol: str
    uid: int
    hotkey: str
    alpha_stake: float  # Stake from this subnet
    tao_stake: float  # Stake from parent network
    stake: float  # Total stake (alpha + tao)
    trust: float  # Trust score
    last_updated: float  # Timestamp of last update


class NodeInfoList(BaseModel):
    """Collection of validator nodes in the subnet."""

    nodes: list[NodeInfo]

    def get_uid(self, hotkey_address: str) -> int:
        """Find the UID for a given hotkey address."""
        for node in self.nodes:
            if node.hotkey == hotkey_address:
                return node.uid
        raise ValueError(f"Hotkey {hotkey_address} not found in metagraph")

    def get_axon(self, hotkey_address: str) -> str:
        """Return http://ip:port for a given hotkey address."""
        for node in self.nodes:
            if node.hotkey == hotkey_address:
                return f"http://{node.ip}:{node.port}"
        raise ValueError(f"Hotkey {hotkey_address} not found in metagraph")
