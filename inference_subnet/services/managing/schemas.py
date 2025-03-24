from pydantic import BaseModel, Field, validator
from typing import List, Dict, Optional, Any


class ConsumeRequest(BaseModel):
    """Request model for consuming rate limits"""

    validator_hotkey: str = Field(..., description="Validator hotkey")
    miner_hotkey: Optional[str] = Field(
        default=None,
        description="Specific miner to consume rate limit for. If None, miners will be sampled.",
    )
    rate_limit_threshold: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Fraction of total rate limit that can be consumed",
    )
    sample_size: int = Field(
        default=1,
        ge=1,
        description="Number of miners to sample when miner_hotkey is not specified",
    )

    top_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Threshold for top score sampling",
    )

    @validator("rate_limit_threshold")
    def validate_threshold(cls, v):
        if v <= 0 or v > 1:
            raise ValueError("Rate limit threshold must be in range (0, 1]")
        return v


class UpdateScoreRequest(BaseModel):
    """Request model for updating miner scores"""

    miner_hotkeys: List[str] = Field(..., description="List of miner hotkeys")
    scores: List[float] = Field(..., description="List of score values")


class MinerSamplingResponse(BaseModel):
    """Response model for miner sampling"""

    miner_hotkeys: List[str] = Field(..., description="List of sampled miner hotkeys")
    uids: List[Optional[int]] = Field(
        ..., description="List of miner UIDs, if available"
    )
    axons: List[Optional[dict]] = Field(
        ..., description="List of miner axon information, if available"
    )


class ScoreEntry(BaseModel):
    """Model for a score history entry"""

    score: float = Field(..., description="Score value")
    timestamp: float = Field(..., description="Unix timestamp when score was recorded")


class MinerScoreHistory(BaseModel):
    """Model for a miner's score history"""

    hotkey: str = Field(..., description="Miner's public key")
    scores: List[ScoreEntry] = Field(default_factory=list, description="Score history")
    average_score: float = Field(..., description="Current average score")


class ScoreResponse(BaseModel):
    """Response model for getting scores"""

    scores: Dict[str, float] = Field(
        ..., description="Mapping of miner hotkeys to their average scores"
    )
