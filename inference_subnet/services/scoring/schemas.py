from pydantic import BaseModel


class ScoreResponse(BaseModel):
    scores: list[float]
