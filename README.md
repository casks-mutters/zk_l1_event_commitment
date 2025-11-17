# README.md
# zk_l1_event_commitment

Overview
zk_l1_event_commitment is a small command-line tool that connects to an EVM-compatible network via web3.py, scans a block range for contract events (logs), and produces a deterministic JSON snapshot plus a Keccak commitment over the event list.

The goal is to export a ZK-friendly artifact that can serve as a public input for:
- Aztec-style rollups that want to constrain L2 state transitions to a specific L1 event stream.
- Zama or other cryptographic experiments that analyze or prove properties about on-chain event flows.
- General soundness-verification systems that bind off-chain logic and proofs to a concrete slice of L1 logs.

The tool:
- Fetches logs for a chosen contract address, optionally filtered by a topic0 (event signature hash).
- Records for each log: block number, transaction hash, log index, topics, and data (hex).
- Sorts events deterministically.
- Computes a Keccak-256 commitment over the ordered event list.

Files
This repository contains exactly two files:
1. app.py — the main script that implements log fetching, summarization, and commitment.
2. README.md — this documentation.

Requirements
- Python 3.10 or newer
- A working EVM-compatible JSON-RPC endpoint (Ethereum, Polygon, Optimism, Arbitrum, Base, etc.)
- Internet access to reach the RPC endpoint
- Python package web3 installed

Installation
Install Python dependencies:
   pip install web3

Configure an RPC endpoint:
   - Option A: set the RPC_URL environment variable, for example:
     export RPC_URL="https://mainnet.infura.io/v3/your_real_key"
   - Option B: pass the RPC URL explicitly via the --rpc flag when running the script.

If RPC_URL is not set and the default value still contains your_api_key, the script will warn you and likely fail to connect until you provide a valid endpoint.

Usage
Basic run: profile events for a contract over the last N blocks (default 200):
   python app.py 0xYourContractAddress

Specify a custom RPC endpoint:
   python app.py 0xYourContractAddress --rpc https://your-evm-rpc

Control the number of recent blocks (when from/to are not provided):
   python app.py 0xYourContractAddress --blocks 500

Set an explicit block window:
   python app.py 0xYourContractAddress --from-block 19000000 --to-block 19001000

Filter by a specific event signature (topic0 Keccak hash, 0x + 64 hex chars):
   python app.py 0xYourContractAddress --topic0 0xd78ad95fa46c994b6551d0da85fc275fe613cece...

Produce pretty-printed JSON for inspection:
   python app.py 0xYourContractAddress --pretty

Disable human-readable logs and emit only JSON to stdout:
   python app.py 0xYourContractAddress --no-human

Behavior and Output
When executed, the script:
1. Connects to the RPC endpoint and prints:
   - Network name and chainId (if known)
   - Current tip (latest block)
   - Connection latency

2. Determines the block range:
   - If --from-block and --to-block are not set, it uses:
     fromBlock = tip - blocks + 1
     toBlock = tip
   - If you supply from/to, they are used (with to clamped to the chain tip if needed).

3. Calls eth_getLogs over the selected block interval:
   - address filter: the specified contract address.
   - topics filter: optional topic0 if provided.

4. For each log, it records:
   - blockNumber
   - txHash
   - logIndex
   - topics (array of hex strings)
   - data (hex string)

5. Sorts all events deterministically by:
   - blockNumber, then
   - txHash, then
   - logIndex.

6. Computes a Keccak-256 commitment over the JSON-serialized, ordered event list.

The final JSON payload printed to stdout has the structure:
- mode: always "zk_l1_event_commitment"
- network: human-readable network name
- chainId: numeric chain ID
- generatedAtUtc: UTC timestamp of generation
- data:
  - address: the contract address
  - fromBlock and toBlock: scanned range (clamped to chain tip)
  - headBlock: current chain tip
  - eventCount: number of logs collected
  - topicsCount: map topic0 -> occurrence count
  - events: array of event objects (blockNumber, txHash, logIndex, topics, data)
  - commitmentKeccak: Keccak-256 hash over the ordered events array
  - elapsedSec: time spent in the eth_getLogs call and processing

ZK / Aztec / Zama / Soundness Context
The commitmentKeccak field is designed to act as a binding reference between:
- A proving or verification system (for example Aztec-style rollup circuits, Zama experiments, or general ZK frameworks).
- A concrete slice of L1 log data.

Typical uses:
- A rollup circuit can import commitmentKeccak as a public input, asserting that its internal event processing corresponds to exactly the events in the committed range.
- A soundness checker can record the payload and commitment alongside proofs, ensuring reproducibility and auditability.
- ZK / HE research scripts can use the JSON as stable input data for simulations, while the commitment provides a short fingerprint of the event set.

Notes and Limitations
- This tool does not verify state or Merkle proofs; it only binds to logs via a Keccak-based commitment.
- The correctness of the snapshot depends on the correctness of the RPC endpoint; for critical use, prefer your own node or multiple sources.
- Large ranges on log-heavy contracts can be expensive; adjust --blocks or the explicit block window to a manageable size.
- Filtering by topic0 is optional but recommended when you are interested in specific events, since it reduces both I/O and event size.

Expected Result
Running the tool with a valid contract and RPC endpoint should yield:
- A short log on stderr describing network, block range, number of events, and final commitment.
- A JSON payload on stdout that can be:
  - Stored, versioned, or archived for future audits.
  - Passed as input to ZK proof generators or soundness pipelines.
  - Compared across runs to ensure that the same event slice is being referenced.
# zk_l1_event_commitment
