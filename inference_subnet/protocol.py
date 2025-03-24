from pydantic import BaseModel, Field


class AddictionPayload(BaseModel):
    a: int = Field(..., description="First number")
    b: int = Field(..., description="Second number")


class AddictionResponse(BaseModel):
    result: int = Field(..., description="Sum of a and b")


class MultiplicationPayload(BaseModel):
    a: int = Field(..., description="First number")
    b: int = Field(..., description="Second number")


class MultiplicationResponse(BaseModel):
    result: int = Field(..., description="Product of a and b")
