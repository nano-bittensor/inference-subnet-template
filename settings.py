from pydantic_settings import BaseSettings
import time


class SubtensorSettings(BaseSettings):
    entrypoint: str = "wss://entrypoint-finney.opentensor.ai:443"
    netuid: int = 47
    sync_node_info_interval: int = 600
    redis_keys: dict[str, str] = {
        "node_infos": "subtensor:{netuid}:node_infos",
    }


class RedisSettings(BaseSettings):
    host: str = "localhost"
    port: int = 6379
    db: int = 0


class QuerySettings(BaseSettings):
    epoch_interval: int = 600
    volume_per_epoch: int = 512
    n_scores_per_epoch: int = 4
    redis_keys: dict[str, str] = {
        "scores_log": "query:{netuid}:scores_log",
        "rate_limit_distribution": "query:{netuid}:rate_limit_distribution",
        "rate_limit_consumed": "query:{netuid}:{epoch}:{miner_hotkey}:{validator_hotkey}:rate_limit_consumed",
    }

    def get_current_epoch(self) -> int:
        return int(time.time() / self.epoch_interval)


class Settings(BaseSettings):
    substrate_sidecar: SubtensorSettings = SubtensorSettings()
    redis: RedisSettings = RedisSettings()
    query: QuerySettings = QuerySettings()

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "."


SETTINGS = Settings()
