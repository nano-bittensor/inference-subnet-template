from fastapi import FastAPI, HTTPException
from inference_subnet.protocol import (
    AddictionPayload,
    AddictionResponse,
    MultiplicationPayload,
    MultiplicationResponse,
)
from inference_subnet.verification import verify_headers
from inference_subnet.settings import SETTINGS

app = FastAPI()


@app.post(SETTINGS.protocol.challenges["addiction"]["api_route"])
async def addiction(
    payload: AddictionPayload, headers: dict[str, str]
) -> AddictionResponse:
    if not verify_headers(headers):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return AddictionResponse(result=payload.a + payload.b)


@app.post(SETTINGS.protocol.challenges["multiplication"]["api_route"])
async def multiplication(
    payload: MultiplicationPayload, headers: dict[str, str]
) -> MultiplicationResponse:
    if not verify_headers(headers):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return MultiplicationResponse(result=payload.a * payload.b)
