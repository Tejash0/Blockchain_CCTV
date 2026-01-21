# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: Blockchain CCTV Evidence Verification - Smart Contract Layer

This is the blockchain layer of a tamper-proof CCTV verification system. It stores SHA-256 hashes of video footage on a local Ethereum blockchain for immutable evidence logging.

## Development Commands

```bash
# Compile smart contracts
npx hardhat compile

# Run all tests
npx hardhat test

# Run specific test by name
npx hardhat test --grep "logEvidence"

# Run tests with gas reporting
REPORT_GAS=true npx hardhat test

# Start local blockchain node (keep running in separate terminal)
npx hardhat node

# Deploy to local network (requires node running)
npx hardhat ignition deploy ./ignition/modules/EvidenceLog.ts --network localhost

# Interactive console with contract access
npx hardhat console --network localhost
```

## Architecture

**Smart Contract:** `contracts/EvidenceLog.sol`
- Stores evidence records as `bytes32` hashes with metadata (cameraId, timestamp, uploader, blockNumber)
- Key functions:
  - `logEvidence(bytes32 _videoHash, string _cameraId, uint256 _timestamp)` - Store new evidence
  - `verifyEvidence(bytes32 _videoHash)` - Check if hash exists (returns bool)
  - `getEvidence(bytes32 _videoHash)` - Get full evidence record
  - `getEvidenceCount()` / `getEvidenceHashAtIndex(uint256)` - Enumeration helpers

**Deployment:** `ignition/modules/EvidenceLog.ts`
- Uses Hardhat Ignition for deployment
- No constructor arguments required

**Tests:** `test/EvidenceLog.ts`
- Uses Chai assertions with Hardhat's ethers integration
- Tests cover: deployment, logging, verification, duplicate prevention, input validation, enumeration

## Critical Details

### Hash Format
All hashes must be `bytes32` (0x + 64 hex characters). When integrating with backend:
```javascript
// Node.js backend
const hash = '0x' + crypto.createHash('sha256').update(buffer).digest('hex');
```

### Network Configuration
- Local: `http://127.0.0.1:8545` (Hardhat node)
- Chain ID: 31337
- Solidity: 0.8.28 with optimizer enabled

### After Deployment
The deployed contract address will be output by Ignition. This address must be configured in the backend's `.env` file as `CONTRACT_ADDRESS`.

## Tech Stack

- Hardhat 2.x (TypeScript)
- Solidity ^0.8.28
- Ethers.js 6.x (via hardhat-toolbox)
- Chai + Mocha for testing
