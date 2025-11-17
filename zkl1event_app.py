# app.py
"""
zk_l1_event_commitment: L1 event log snapshot for ZK / soundness systems.

This script:
  - Connects to an EVM-compatible network via web3.py
  - Scans a block range for logs (events) of a given contract (and optional topic)
  - Collects a compact summary of events and their block numbers
  - Computes a Keccak commitment over the event list

The resulting JSON payload can be used as:
  - A public input to Aztec-style rollup circuits
  - A soundness witness that binds L2 state transitions to L1 event streams
  - An artifact for Zama-style cryptographic / ZK research on event-based protocols
"""

import os
import sys
import json
import time
import argparse
from typing import Any, Dict, List, Optional

from web3 import Web3

DEFAULT_RPC = os.getenv("RPC_URL", "https://mainnet.infura.io/v3/your_api_key")
DEFAULT_BLOCKS = int(os.getenv("ZK_EVENT_BLOCKS", "200"))

NETWORKS: Dict[int, str] = {
    1: "Ethereum Mainnet",
    11155111: "Sepolia Testnet",
    10: "Optimism",
    137: "Polygon",
    42161: "Arbitrum One",
    8453: "Base",
}


def network_name(cid: int) -> str:
    return NETWORKS.get(cid, f"Unknown (chain ID {cid})")


def connect(rpc: str) -> Web3:
    start = time.time()
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 25}))

    if not w3.is_connected():
        print(f"❌ Failed to connect to RPC endpoint: {rpc}", file=sys.stderr)
        sys.exit(1)

    latency = time.time() - start
    try:
        cid = int(w3.eth.chain_id)
        tip = int(w3.eth.block_number)
        print(
            f"🌐 Connected to {network_name(cid)} (chainId {cid}, tip={tip}) in {latency:.2f}s",
            file=sys.stderr,
        )
    except Exception:
        print(f"🌐 Connected to RPC (chain info unavailable) in {latency:.2f}s", file=sys.stderr)

    return w3


def normalize_address(addr: str) -> str:
    try:
        return Web3.to_checksum_address(addr.strip())
    except Exception:
        raise ValueError(f"Invalid address: {addr!r}")


def normalize_topic(topic: str) -> str:
    topic = topic.strip()
    if not topic:
        raise ValueError("Empty topic string")
    if not topic.startswith("0x"):
        raise ValueError(f"Topic must be hex starting with 0x, got: {topic!r}")
    if len(topic) != 66:
        raise ValueError(
            f"Topic must be 32-byte keccak hex (0x + 64 chars). Got length {len(topic)}."
        )
    return topic.lower()


def fetch_events(
    w3: Web3,
    address: str,
    from_block: int,
    to_block: int,
    topic0: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch logs for a contract over a block range and compute a Keccak commitment."""
    if from_block > to_block:
        from_block, to_block = to_block, from_block

    head = int(w3.eth.block_number)
    to_block_clamped = min(to_block, head)

    print(
        f"🔍 Fetching logs for {address} in blocks [{from_block}, {to_block_clamped}]...",
        file=sys.stderr,
    )

    filter_kwargs: Dict[str, Any] = {
        "address": address,
        "fromBlock": from_block,
        "toBlock": to_block_clamped,
    }

    if topic0:
        filter_kwargs["topics"] = [topic0]

    t0 = time.time()
    logs = w3.eth.get_logs(filter_kwargs)
    elapsed = time.time() - t0

    events: List[Dict[str, Any]] = []
    topics_seen: Dict[str, int] = {}

    for idx, lg in enumerate(logs, 1):
        block_num = int(lg["blockNumber"])
        tx_hash = Web3.to_hex(lg["transactionHash"])
        log_index = int(lg["logIndex"])
        topics = [Web3.to_hex(t) for t in lg["topics"]]
        data_hex = Web3.to_hex(lg["data"])

        topic0_hex = topics[0] if topics else None
        if topic0_hex:
            topics_seen[topic0_hex] = topics_seen.get(topic0_hex, 0) + 1

        events.append(
            {
                "blockNumber": block_num,
                "txHash": tx_hash,
                "logIndex": log_index,
                "topics": topics,
                "data": data_hex,
            }
        )

        if idx % 50 == 0:
            print(f"   ⏳ processed {idx}/{len(logs)} logs...", file=sys.stderr)

    # Sort events deterministically for commitment stability
    events.sort(key=lambda e: (e["blockNumber"], e["txHash"], e["logIndex"]))

    # Compute Keccak commitment over the ordered events
    encoded = json.dumps(events, sort_keys=True, separators=(",", ":")).encode()
    commitment = Web3.keccak(encoded).hex()

    return {
        "address": address,
        "fromBlock": from_block,
        "toBlock": to_block_clamped,
        "headBlock": head,
        "eventCount": len(events),
        "topicsCount": topics_seen,
        "events": events,
        "commitmentKeccak": commitment,
        "elapsedSec": round(elapsed, 3),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an L1 event-log snapshot + Keccak commitment for ZK/soundness systems.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "address",
        help="Contract address whose events are to be profiled.",
    )
    parser.add_argument(
        "--topic0",
        help="Optional topic0 (event signature hash, 0x + 64 hex chars) to filter logs.",
    )
    parser.add_argument(
        "--rpc",
        default=DEFAULT_RPC,
        help="RPC URL (default from RPC_URL env).",
    )
    parser.add_argument(
        "--from-block",
        type=int,
        help="Start block (defaults to tip - ZK_EVENT_BLOCKS).",
    )
    parser.add_argument(
        "--to-block",
        type=int,
        help="End block (defaults to chain tip).",
    )
    parser.add_argument(
        "--blocks",
        type=int,
        default=DEFAULT_BLOCKS,
        help="Number of recent blocks if from/to are not provided.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON instead of compact output.",
    )
    parser.add_argument(
        "--no-human",
        action="store_true",
        help="Disable human summary (JSON only).",
    )
    return parser.parse_args()


def main() -> None:
    if "your_api_key" in DEFAULT_RPC:
        print(
            "⚠️  RPC_URL is not set and DEFAULT_RPC still uses a placeholder key. "
            "Set RPC_URL or pass --rpc.",
            file=sys.stderr,
        )

    args = parse_args()

    try:
        addr = normalize_address(args.address)
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

    topic0 = None
    if args.topic0:
        try:
            topic0 = normalize_topic(args.topic0)
        except ValueError as e:
            print(f"❌ {e}", file=sys.stderr)
            sys.exit(1)

    if args.blocks <= 0:
        print("❌ --blocks must be > 0", file=sys.stderr)
        sys.exit(1)

    w3 = connect(args.rpc)
    tip = int(w3.eth.block_number)

    if args.from_block is None and args.to_block is None:
        to_block = tip
        from_block = max(0, tip - args.blocks + 1)
    else:
        to_block = args.to_block if args.to_block is not None else tip
        from_block = args.from_block if args.from_block is not None else max(
            0, to_block - args.blocks + 1
        )

    print(
        f"📅 zk_l1_event_commitment started at UTC {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}",
        file=sys.stderr,
    )
    print(
        f"🔗 Using RPC endpoint: {args.rpc}  |  contract={addr}",
        file=sys.stderr,
    )

    t0 = time.time()
    snapshot = fetch_events(
        w3=w3,
        address=addr,
        from_block=int(from_block),
        to_block=int(to_block),
        topic0=topic0,
    )
    elapsed = time.time() - t0

    chain_id = int(w3.eth.chain_id)
    payload = {
        "mode": "zk_l1_event_commitment",
        "network": network_name(chain_id),
        "chainId": chain_id,
        "generatedAtUtc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "data": snapshot,
    }

    if not args.no_human:
        print(
            f"🌐 {payload['network']} (chainId {payload['chainId']}) "
            f"blocks [{snapshot['fromBlock']}, {snapshot['toBlock']}] "
            f"events={snapshot['eventCount']}",
            file=sys.stderr,
        )
        print(
            f"🔐 CommitmentKeccak: {snapshot['commitmentKeccak']}",
            file=sys.stderr,
        )
        print(
            f"⏱️  Snapshot generation took {elapsed:.2f}s (logs only: {snapshot['elapsedSec']}s)",
            file=sys.stderr,
        )
        print(
            "ℹ️  This commitment can be integrated into Aztec/Zama-style ZK circuits "
            "to bind off-chain logic to an L1 event stream.",
            file=sys.stderr,
        )

    if args.pretty:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
