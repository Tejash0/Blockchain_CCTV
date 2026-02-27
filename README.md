# Blockchain-Based CCTV Evidence Verification System

A tamper-proof surveillance verification system that stores cryptographic hashes of video footage on a local Ethereum blockchain. The system uses a **dual-hash strategy** — SHA-256 for exact integrity and K2A-Hash (a novel perceptual hash) for content-level tamper detection — anchored immutably in a Solidity smart contract.

## Core Innovation: K2A-Hash

**K2A-Hash** is a novel perceptual hashing algorithm combining:
- Uniform 8×8 block grid diagonal pixel extraction
- Directional bit compression (L→R vs R→L asymmetry)
- Complement-based self-verification (`K XOR ~K = 0xFFFFFFFF`)
- Temporal frame-index coupling for deepfake/frame-substitution detection

SHA-256 alone detects file corruption. K2A-Hash detects **semantic content changes** (deepfakes, frame substitution) that leave the file size identical but alter visual content.

## Architecture

```
Camera/AI Service → Backend API → SQLite Cache ← → Blockchain (Hardhat EVM)
                                       ↑
                                  Frontend (React)
```

Four components run concurrently:

| Component | Location | Port | Purpose |
|-----------|----------|------|---------|
| Hardhat Blockchain | `blockchain/` (project root) | 8545 | Immutable evidence anchor |
| Backend API | `backend/` | 5000 | Hash ingestion, verification, SQL cache |
| Frontend | `frontend/` | 5173 | Dashboard, verifier, tamper demo |
| AI Service | `ai-service/` | 8000 | K2A-Hash computation, crime detection |

## Prerequisites

- **Node.js** v18+ (v25 recommended)
- **Python** 3.10+ with `pip`
- **npm** (or pnpm/yarn)
- **pdflatex** (optional, for building the paper)

## Quick Start (3 Terminals)

### Terminal 1 — Blockchain Node
```bash
# Start local Hardhat EVM
npx hardhat node

# In a separate shell, deploy the contract (first time only):
npx hardhat ignition deploy ./ignition/modules/EvidenceLog.ts --network localhost
```

### Terminal 2 — Backend API
```bash
cd backend
npm install

# Copy and edit environment variables
cp .env.example .env
# Set CONTRACT_ADDRESS from the deployment output above
# Set PRIVATE_KEY to a Hardhat test account key

node server.js
```

### Terminal 3 — Frontend
```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

### Optional: AI Service
```bash
cd ai-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Environment Variables (Backend)

Create `backend/.env`:
```env
PORT=5000
DATABASE_PATH=./database/evidence.db
HARDHAT_NETWORK_URL=http://127.0.0.1:8545
CONTRACT_ADDRESS=<from hardhat ignition deploy output>
PRIVATE_KEY=<hardhat test account private key>
CORS_ORIGIN=http://localhost:5173
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/record` | Ingest video hash + metadata → SQL + blockchain |
| `POST` | `/api/verify` | Two-level verification (SQL cache + blockchain) |
| `GET`  | `/api/logs`   | Paginated evidence log with status |

### POST /api/record
```json
{
  "videoHash": "0x<sha256>",
  "cameraId": "CAM-01",
  "timestamp": 1700000000,
  "perceptualHash": "0x<k2a-hash>",
  "eventType": "violence",
  "confidenceScore": 9200
}
```

### POST /api/verify
```json
{ "videoHash": "0x<sha256>" }
```
Returns:
```json
{
  "verified": true,
  "level": "blockchain",
  "k2a_hamming_distance": 3,
  "k2a_verdict": "content_authentic"
}
```

## Verification Logic

1. **Level 1 (SQL cache):** Sub-second lookup of stored hash
2. **Level 2 (blockchain):** On-chain `verifyEvidence()` call
3. **K2A verdict:** Hamming distance ≤ 8 bits → `content_authentic`; > 8 bits → `content_modified`

## Smart Contract

`EvidenceLog.sol` stores per evidence entry:
- `bytes32 videoHash` — SHA-256 of video file
- `bytes32 perceptualHash` — K2A-Hash (content fingerprint)
- `bytes32 reportHash` — SHA-256 of AI forensic report
- `string cameraId`, `uint256 timestamp`, `address uploader`

## Project Structure

```
blockchain-cctv/
├── contracts/          # Solidity smart contracts
│   └── EvidenceLog.sol
├── ignition/           # Hardhat Ignition deployment modules
├── backend/            # Node.js + Express API + SQLite
│   ├── server.js
│   └── database/
├── frontend/           # React 18 + Vite + Tailwind
│   └── src/
├── ai-service/         # FastAPI + Python K2A-Hash + Gemini AI
│   └── app/
│       └── utils/
│           └── k2a_hash.py
├── cloud-storage/      # Local clip storage (runtime)
├── docs/               # Research paper and academic artifacts
│   ├── paper/
│   │   └── paper.tex
│   ├── res/
│   ├── references/
│   └── K2A_NOVELTY_ANALYSIS.md
├── test/               # Hardhat contract tests
├── hardhat.config.ts
└── package.json
```

## Running Tests

```bash
# Smart contract tests
npx hardhat test

# With gas reporting
REPORT_GAS=true npx hardhat test
```

## Building the Paper

```bash
cd docs/paper
pdflatex paper.tex
bibtex paper
pdflatex paper.tex
pdflatex paper.tex
```

## Key Design Decisions

- **EVM over Hyperledger Fabric:** JSON-RPC is lightweight vs Docker/Java overhead; Solidity is industry-standard
- **Two-level verification:** SQL for speed (< 1s), blockchain for immutable truth (< 5s)
- **Hash-only storage:** 32 bytes on-chain vs GB-sized videos; preserves privacy
- **K2A + SHA-256 dual hash:** SHA-256 catches byte-level changes; K2A catches semantic content changes

## License

Academic project — Mini Project 2026.
