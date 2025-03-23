from pydantic import BaseModel
from pydantic_settings import BaseSettings
import time
import os


class SubtensorSettings(BaseModel):
    entrypoint: str = "wss://entrypoint-finney.opentensor.ai:443"
    netuid: int = 47
    sync_node_info_interval: int = 600
    redis_keys: dict[str, str] = {
        "node_infos": "subtensor:{netuid}:node_infos",
    }
    host: str = "127.0.0.1"
    port: int = 9001
    adapter: str = "http"
    request_timeout: float = 10.0  # Timeout for HTTP requests to sidecar

    @property
    def base_url(self) -> str:
        return f"{self.adapter}://{self.host}:{self.port}"


class WalletSettings(BaseModel):
    hotkey: str = "default"
    name: str = "default"
    wallet_path: str = "~/.bittensor/wallets"

    @property
    def wallet_file(self) -> str:
        return os.path.join(
            os.path.expanduser(self.wallet_path), self.name, "hotkeys", self.hotkey
        )


class RedisSettings(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0


class QuerySettings(BaseModel):
    epoch_interval: int = 600
    n_scores_per_epoch: int = 4
    n_historical_scores: int = 10
    score_history_ttl_factor: int = 2  # Multiplier for score history TTL
    # Rate limiting settings
    rate_limit_min_stake: int = 1000  # Minimum stake required for rate limiting
    rate_limit_max_requests: int = 256  # Maximum rate limit per epoch
    redis_keys: dict[str, str] = {
        "scores_history": "scores:history:{miner_hotkey}",
        "scores_average": "scores:average:{miner_hotkey}",
        "rate_limits": "rate_limits:global",
        "rate_limits_consumed": "rate_limits:consumed:{epoch}:{miner_hotkey}",
        "rate_limits_consumed_global": "rate_limits:consumed:{epoch}",
    }

    def get_current_epoch(self) -> int:
        return int(time.time() / self.epoch_interval)


class Settings(BaseSettings):
    substrate_sidecar: SubtensorSettings = SubtensorSettings()
    wallet: WalletSettings = WalletSettings()
    redis: RedisSettings = RedisSettings()
    query: QuerySettings = QuerySettings()

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "."
        extra = "ignore"  # Ignore additional env variables in .env


SETTINGS = Settings()

print(SETTINGS)
