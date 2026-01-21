import express from 'express';
import cors from 'cors';
import multer from 'multer';
import crypto from 'crypto';
import { ethers } from 'ethers';
import Database from 'better-sqlite3';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';

// Load environment variables
dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Configuration
const PORT = process.env.PORT || 5000;
const DATABASE_PATH = process.env.DATABASE_PATH || './database/evidence.db';
const HARDHAT_NETWORK_URL = process.env.HARDHAT_NETWORK_URL || 'http://127.0.0.1:8545';
const CONTRACT_ADDRESS = process.env.CONTRACT_ADDRESS;
const PRIVATE_KEY = process.env.PRIVATE_KEY;

// Contract ABI (relevant functions only)
const CONTRACT_ABI = [
  "function logEvidence(bytes32 _videoHash, string _cameraId, uint256 _timestamp) external",
  "function verifyEvidence(bytes32 _videoHash) external view returns (bool exists)",
  "function getEvidence(bytes32 _videoHash) external view returns (tuple(bytes32 videoHash, string cameraId, uint256 timestamp, address uploader, uint256 blockNumber, uint256 loggedAt))",
  "function getEvidenceCount() external view returns (uint256 count)",
  "function getEvidenceHashAtIndex(uint256 _index) external view returns (bytes32 hash)",
  "event EvidenceLogged(bytes32 indexed videoHash, string cameraId, uint256 timestamp, address indexed uploader, uint256 blockNumber)"
];

// Initialize Express
const app = express();

// Middleware
app.use(cors({
  origin: ['http://localhost:5173', 'http://127.0.0.1:5173'],
  methods: ['GET', 'POST'],
  credentials: true
}));
app.use(express.json());

// Configure multer for file uploads
const upload = multer({
  storage: multer.memoryStorage(),
  limits: {
    fileSize: 100 * 1024 * 1024 // 100MB limit
  }
});

// Initialize SQLite database
const db = new Database(path.resolve(__dirname, DATABASE_PATH));
db.pragma('journal_mode = WAL');

// Create tables
db.exec(`
  CREATE TABLE IF NOT EXISTS evidence_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_hash TEXT NOT NULL UNIQUE,
    camera_id TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    blockchain_tx TEXT,
    block_number INTEGER,
    uploader TEXT,
    status TEXT CHECK(status IN ('pending', 'confirmed', 'failed')) DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX IF NOT EXISTS idx_video_hash ON evidence_log(video_hash);
  CREATE INDEX IF NOT EXISTS idx_status ON evidence_log(status);
`);

// Prepared statements
const insertEvidence = db.prepare(`
  INSERT INTO evidence_log (video_hash, camera_id, timestamp, status)
  VALUES (?, ?, ?, 'pending')
`);

const updateEvidenceConfirmed = db.prepare(`
  UPDATE evidence_log
  SET status = 'confirmed', blockchain_tx = ?, block_number = ?, uploader = ?
  WHERE video_hash = ?
`);

const updateEvidenceFailed = db.prepare(`
  UPDATE evidence_log SET status = 'failed' WHERE video_hash = ?
`);

const getEvidenceByHash = db.prepare(`
  SELECT * FROM evidence_log WHERE video_hash = ?
`);

const getAllEvidence = db.prepare(`
  SELECT * FROM evidence_log ORDER BY created_at DESC
`);

// Initialize blockchain connection
let provider;
let wallet;
let contract;

async function initBlockchain() {
  try {
    provider = new ethers.JsonRpcProvider(HARDHAT_NETWORK_URL);

    if (!PRIVATE_KEY) {
      console.error('ERROR: PRIVATE_KEY not set in .env file');
      return false;
    }

    if (!CONTRACT_ADDRESS) {
      console.error('ERROR: CONTRACT_ADDRESS not set in .env file');
      return false;
    }

    wallet = new ethers.Wallet(PRIVATE_KEY, provider);
    contract = new ethers.Contract(CONTRACT_ADDRESS, CONTRACT_ABI, wallet);

    // Test connection
    const network = await provider.getNetwork();
    console.log(`Connected to blockchain network: Chain ID ${network.chainId}`);
    console.log(`Contract address: ${CONTRACT_ADDRESS}`);
    console.log(`Wallet address: ${wallet.address}`);

    return true;
  } catch (error) {
    console.error('Failed to initialize blockchain connection:', error.message);
    return false;
  }
}

// Helper function to calculate SHA-256 hash
function calculateHash(buffer) {
  const hash = crypto.createHash('sha256').update(buffer).digest('hex');
  return '0x' + hash;
}

// Helper function to validate hash format
function isValidHash(hash) {
  return /^0x[a-fA-F0-9]{64}$/.test(hash);
}

// API Routes

/**
 * POST /api/record
 * Upload video file, hash it, store on blockchain
 */
app.post('/api/record', upload.single('video'), async (req, res) => {
  try {
    // Validate input
    if (!req.file) {
      return res.status(400).json({
        success: false,
        error: 'No video file provided'
      });
    }

    const cameraId = req.body.cameraId;
    if (!cameraId || cameraId.trim() === '') {
      return res.status(400).json({
        success: false,
        error: 'Camera ID is required'
      });
    }

    // Calculate hash of the file
    const videoHash = calculateHash(req.file.buffer);
    const timestamp = Math.floor(Date.now() / 1000);

    console.log(`Recording evidence: hash=${videoHash}, cameraId=${cameraId}`);

    // Check if already exists in database
    const existing = getEvidenceByHash.get(videoHash);
    if (existing) {
      return res.status(409).json({
        success: false,
        error: 'Evidence with this hash already exists',
        existing: {
          videoHash: existing.video_hash,
          cameraId: existing.camera_id,
          status: existing.status
        }
      });
    }

    // Insert into database with pending status
    try {
      insertEvidence.run(videoHash, cameraId.trim(), timestamp);
    } catch (dbError) {
      if (dbError.code === 'SQLITE_CONSTRAINT_UNIQUE') {
        return res.status(409).json({
          success: false,
          error: 'Evidence already exists in database'
        });
      }
      throw dbError;
    }

    // Submit to blockchain
    try {
      const tx = await contract.logEvidence(videoHash, cameraId.trim(), timestamp);
      console.log(`Transaction submitted: ${tx.hash}`);

      const receipt = await tx.wait();
      console.log(`Transaction confirmed in block ${receipt.blockNumber}`);

      // Update database with confirmation
      updateEvidenceConfirmed.run(
        receipt.hash,
        receipt.blockNumber,
        wallet.address,
        videoHash
      );

      return res.json({
        success: true,
        videoHash,
        txHash: receipt.hash,
        blockNumber: receipt.blockNumber,
        cameraId: cameraId.trim(),
        timestamp
      });

    } catch (blockchainError) {
      console.error('Blockchain error:', blockchainError.message);

      // Update database with failed status
      updateEvidenceFailed.run(videoHash);

      // Check if it's a duplicate hash error from contract
      if (blockchainError.message.includes('Evidence already exists')) {
        return res.status(409).json({
          success: false,
          error: 'Evidence already exists on blockchain'
        });
      }

      return res.status(500).json({
        success: false,
        error: 'Failed to record on blockchain: ' + blockchainError.message
      });
    }

  } catch (error) {
    console.error('Record error:', error);
    return res.status(500).json({
      success: false,
      error: 'Internal server error: ' + error.message
    });
  }
});

/**
 * POST /api/verify
 * Upload video file, verify against blockchain
 */
app.post('/api/verify', upload.single('video'), async (req, res) => {
  try {
    // Validate input
    if (!req.file) {
      return res.status(400).json({
        verified: false,
        error: 'No video file provided'
      });
    }

    // Calculate hash of the file
    const videoHash = calculateHash(req.file.buffer);
    console.log(`Verifying evidence: hash=${videoHash}`);

    // Level 1: Check SQL cache
    const cachedEvidence = getEvidenceByHash.get(videoHash);

    // Level 2: Verify on blockchain
    try {
      const exists = await contract.verifyEvidence(videoHash);

      if (exists) {
        // Get full evidence from blockchain
        const evidence = await contract.getEvidence(videoHash);

        const result = {
          verified: true,
          source: cachedEvidence ? 'cache+blockchain' : 'blockchain',
          evidence: {
            videoHash: evidence.videoHash,
            cameraId: evidence.cameraId,
            timestamp: Number(evidence.timestamp),
            uploader: evidence.uploader,
            blockNumber: Number(evidence.blockNumber),
            loggedAt: Number(evidence.loggedAt)
          }
        };

        // If not in cache, add it
        if (!cachedEvidence) {
          try {
            insertEvidence.run(videoHash, evidence.cameraId, Number(evidence.timestamp));
            updateEvidenceConfirmed.run(
              null, // No tx hash for discovered evidence
              Number(evidence.blockNumber),
              evidence.uploader,
              videoHash
            );
          } catch (e) {
            // Ignore if already exists
          }
        }

        return res.json(result);
      } else {
        // Not found on blockchain
        return res.json({
          verified: false,
          videoHash,
          message: cachedEvidence && cachedEvidence.status === 'pending'
            ? 'Evidence found in cache but not yet confirmed on blockchain'
            : 'Evidence not found on blockchain'
        });
      }

    } catch (blockchainError) {
      console.error('Blockchain verification error:', blockchainError.message);

      // Fall back to cache if blockchain unavailable
      if (cachedEvidence && cachedEvidence.status === 'confirmed') {
        return res.json({
          verified: true,
          source: 'cache-only',
          warning: 'Blockchain verification failed, using cached data',
          evidence: {
            videoHash: cachedEvidence.video_hash,
            cameraId: cachedEvidence.camera_id,
            timestamp: cachedEvidence.timestamp,
            uploader: cachedEvidence.uploader,
            blockNumber: cachedEvidence.block_number
          }
        });
      }

      return res.status(500).json({
        verified: false,
        error: 'Blockchain verification failed: ' + blockchainError.message
      });
    }

  } catch (error) {
    console.error('Verify error:', error);
    return res.status(500).json({
      verified: false,
      error: 'Internal server error: ' + error.message
    });
  }
});

/**
 * GET /api/logs
 * Get all evidence records from blockchain
 */
app.get('/api/logs', async (req, res) => {
  try {
    // Get count from blockchain
    const count = await contract.getEvidenceCount();
    const totalCount = Number(count);

    console.log(`Fetching ${totalCount} evidence records from blockchain`);

    const records = [];

    // Fetch all evidence from blockchain
    for (let i = 0; i < totalCount; i++) {
      try {
        const hash = await contract.getEvidenceHashAtIndex(i);
        const evidence = await contract.getEvidence(hash);

        records.push({
          videoHash: evidence.videoHash,
          cameraId: evidence.cameraId,
          timestamp: Number(evidence.timestamp),
          uploader: evidence.uploader,
          blockNumber: Number(evidence.blockNumber),
          loggedAt: Number(evidence.loggedAt)
        });
      } catch (e) {
        console.error(`Error fetching evidence at index ${i}:`, e.message);
      }
    }

    // Sort by timestamp descending (newest first)
    records.sort((a, b) => b.timestamp - a.timestamp);

    return res.json({
      success: true,
      count: records.length,
      records
    });

  } catch (error) {
    console.error('Logs error:', error);

    // Fall back to database cache
    try {
      const cachedRecords = getAllEvidence.all();
      return res.json({
        success: true,
        source: 'cache',
        warning: 'Blockchain unavailable, showing cached records',
        count: cachedRecords.length,
        records: cachedRecords.map(r => ({
          videoHash: r.video_hash,
          cameraId: r.camera_id,
          timestamp: r.timestamp,
          uploader: r.uploader,
          blockNumber: r.block_number,
          status: r.status
        }))
      });
    } catch (dbError) {
      return res.status(500).json({
        success: false,
        error: 'Failed to fetch logs: ' + error.message
      });
    }
  }
});

/**
 * GET /api/health
 * Health check endpoint
 */
app.get('/api/health', async (req, res) => {
  try {
    const blockNumber = await provider.getBlockNumber();
    return res.json({
      status: 'ok',
      blockchain: 'connected',
      blockNumber,
      contractAddress: CONTRACT_ADDRESS
    });
  } catch (error) {
    return res.json({
      status: 'degraded',
      blockchain: 'disconnected',
      error: error.message
    });
  }
});

// Start server
async function start() {
  const blockchainReady = await initBlockchain();

  if (!blockchainReady) {
    console.warn('WARNING: Starting server without blockchain connection');
    console.warn('Make sure Hardhat node is running and .env is configured');
  }

  app.listen(PORT, () => {
    console.log(`Backend server running on http://localhost:${PORT}`);
    console.log('Endpoints:');
    console.log(`  POST /api/record - Record new evidence`);
    console.log(`  POST /api/verify - Verify evidence`);
    console.log(`  GET  /api/logs   - Get all evidence logs`);
    console.log(`  GET  /api/health - Health check`);
  });
}

start();
