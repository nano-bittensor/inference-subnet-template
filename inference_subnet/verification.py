from substrateinterface import Keypair
import time
from loguru import logger


def create_message(miner_hotkey: str, keypair: Keypair) -> str:
    nonce = time.time_ns()
    return f"{miner_hotkey}:{keypair.ss58_address}:{nonce}"


def create_headers(keypair: Keypair, miner_hotkey: str) -> dict[str, str]:
    message = create_message(miner_hotkey, keypair)
    signature = keypair.sign(message.encode("utf-8"))
    signature = f"0x{signature.hex()}"
    return {
        "BT_MESSAGE": message,
        "BT_SIGNATURE": signature,
    }


def verify_headers(headers: dict[str, str], keypair: Keypair) -> bool:
    message = headers["BT_MESSAGE"]
    signature = headers["BT_SIGNATURE"]
    miner_hotkey, validator_hotkey, nonce = message.split(":")
    if miner_hotkey != keypair.ss58_address:
        logger.error(f"Miner hotkey mismatch: {miner_hotkey} != {keypair.ss58_address}")
        return False
    if validator_hotkey != validator_hotkey:
        logger.error(
            f"Validator hotkey mismatch: {validator_hotkey} != {validator_hotkey}"
        )
        return False
    if (time.time_ns() - int(nonce)) / 1e9 > 32:
        logger.error(f"Nonce too old: {nonce}")
        return False
    if not keypair.verify(message.encode("utf-8"), signature):
        logger.error(f"Signature verification failed: {signature}")
        return False
    return True
