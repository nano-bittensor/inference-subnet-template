# Reference to Fiber - RayonLabs https://github.com/rayonlabs/fiber/blob/production/fiber/chain/post_ip_to_chain.py
import netaddr
from substrateinterface import Keypair, SubstrateInterface
from tenacity import retry, stop_after_attempt, wait_exponential
import argparse
import json
import os
from loguru import logger

NETWORK_MAP = {
    "finney": "wss://entrypoint-finney.opentensor.ai:443",
}


def parse_arguments():
    parser = argparse.ArgumentParser(description="Post node IP to blockchain.")
    parser.add_argument(
        "--wallet-hotkey", type=str, required=True, help="Hotkey for the wallet."
    )
    parser.add_argument(
        "--wallet-name", type=str, required=True, help="Name of the wallet."
    )
    parser.add_argument(
        "--wallet-path", type=str, required=True, help="Path to the wallet directory."
    )
    parser.add_argument("--netuid", type=int, required=True, help="Network UID.")
    parser.add_argument("--network", type=str, required=True, help="Network name.")
    parser.add_argument(
        "--external-ip", type=str, required=True, help="External IP address."
    )
    parser.add_argument(
        "--external-port", type=int, required=True, help="External port number."
    )
    args = parser.parse_args()
    args.network = NETWORK_MAP.get(args.network, args.network)
    return args


def convert_ip_to_int(ip_address: str) -> int:
    return int(netaddr.IPAddress(ip_address))


def get_ip_version(ip_address: str) -> int:
    """Returns the IP version (IPv4 or IPv6)."""
    return int(netaddr.IPAddress(ip_address).version)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4))
def post_ip_to_blockchain(
    substrate: SubstrateInterface,
    keypair: Keypair,
    netuid: int,
    external_ip: str,
    external_port: int,
    coldkey_ss58_address: str,
    wait_for_inclusion=False,
    wait_for_finalization=True,
) -> bool:
    params = {
        "version": 1,
        "ip": convert_ip_to_int(external_ip),
        "port": external_port,
        "ip_type": get_ip_version(external_ip),
        "netuid": netuid,
        "hotkey": keypair.ss58_address,
        "coldkey": coldkey_ss58_address,
        "protocol": 4,
        "placeholder1": 0,
        "placeholder2": 0,
    }

    logger.info(f"Posting IP to blockchain. Params: {params}")

    with substrate as si:
        call = si.compose_call("SubtensorModule", "serve_axon", params)
        extrinsic = si.create_signed_extrinsic(call=call, keypair=keypair)
        response = si.submit_extrinsic(
            extrinsic, wait_for_inclusion, wait_for_finalization
        )

        if wait_for_inclusion or wait_for_finalization:
            response.process_events()
            if not response.is_success:
                logger.error(f"Failed: {response.error_message}")
            return response.is_success
    return True


def main():
    args = parse_arguments()
    wallet_file_path = os.path.join(
        os.path.expanduser(args.wallet_path),
        args.wallet_name,
        "hotkeys",
        args.wallet_hotkey,
    )
    with open(wallet_file_path) as wallet_file:
        seed = json.load(wallet_file)["secretSeed"]
    keypair = Keypair.create_from_seed(seed)

    coldkey_pub_file_path = os.path.join(
        os.path.expanduser(args.wallet_path),
        args.wallet_name,
        "coldkeypub.txt",
    )
    with open(coldkey_pub_file_path) as coldkey_pub_file:
        coldkey_pub = json.load(coldkey_pub_file)["ss58Address"]

    logger.info(f"Keypair: {keypair.ss58_address}")

    substrate = SubstrateInterface(
        url=args.network,
        ss58_format=42,
    )

    post_ip_to_blockchain(
        substrate=substrate,
        keypair=keypair,
        netuid=args.netuid,
        external_ip=args.external_ip,
        external_port=args.external_port,
        coldkey_ss58_address=coldkey_pub,
    )


if __name__ == "__main__":
    main()
