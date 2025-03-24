from pydantic import BaseModel
from pydantic_settings import BaseSettings
import time
import os
from inference_subnet.protocol import (
    AddictionPayload,
    AddictionResponse,
    MultiplicationPayload,
    MultiplicationResponse,
)
import random
from typing import Any


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


class ManagingSettings(BaseModel):
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
    host: str = "127.0.0.1"
    port: int = 9002

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def get_current_epoch(self) -> int:
        return int(time.time() / self.epoch_interval)


class ValidatingSettings(BaseModel):
    batch_size: int = 4
    synthetic_rate_limit_threshold: float = 0.3
    dropout_scoring_enabled: bool = True
    max_scores_per_period: int = 4
    score_period_seconds: int = 600
    score_tracking_key_prefix: str = "validator:score_tracking:"
    scoring_semaphore_size: int = 16


class ProtocolSettings(BaseModel):
    challenges: dict[str, dict[str, Any]] = {
        "addiction": {
            "payload_model": AddictionPayload,
            "response_model": AddictionResponse,
            "api_route": "/api/add",
        },
        "multiplication": {
            "payload_model": MultiplicationPayload,
            "response_model": MultiplicationResponse,
            "api_route": "/api/multiply",
        },
    }
    timeout: float = 12.0

    @property
    def sample_challenge(self) -> tuple[str, BaseModel, BaseModel]:
        challenge = random.choice(list(self.challenges.keys()))
        return (
            challenge,
            self.challenges[challenge]["payload_model"],
            self.challenges[challenge]["response_model"],
            self.challenges[challenge]["api_route"],
        )


class ScoringSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 9003

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


class SynthesizingSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 9004

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


class Settings(BaseSettings):
    substrate_sidecar: SubtensorSettings = SubtensorSettings()
    wallet: WalletSettings = WalletSettings()
    redis: RedisSettings = RedisSettings()
    managing: ManagingSettings = ManagingSettings()
    validating: ValidatingSettings = ValidatingSettings()
    scoring: ScoringSettings = ScoringSettings()
    synthesizing: SynthesizingSettings = SynthesizingSettings()
    protocol: ProtocolSettings = ProtocolSettings()

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "."
        extra = "ignore"  # Ignore additional env variables in .env


SETTINGS = Settings()

print(SETTINGS)
