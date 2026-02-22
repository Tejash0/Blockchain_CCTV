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

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Configuration
const PORT = process.env.PORT || 5000;
const DATABASE_PATH = process.env.DATABASE_PATH || './database/evidence.db';
const HARDHAT_NETWORK_URL = process.env.HARDHAT_NETWORK_URL || 'http://127.0.0.1:8545';
const CONTRACT_ADDRESS = process.env.CONTRACT_ADDRESS;
const PRIVATE_KEY = process.env.PRIVATE_KEY;

// Cloud storage directories
const CLOUD_STORAGE_ROOT = path.resolve(__dirname, '..', 'cloud-storage');
const CLIPS_DIR = path.join(CLOUD_STORAGE_ROOT, 'clips');
const REPORTS_DIR = path.join(CLOUD_STORAGE_ROOT, 'reports');

// Ensure cloud storage directories exist
[CLIPS_DIR, REPORTS_DIR].forEach(dir => {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});

// Contract ABI (updated with new fields)
const CONTRACT_ABI = [
  "function logEvidence(bytes32 _videoHash, string _cameraId, uint256 _timestamp, bytes32 _reportHash, bytes32 _perceptualHash, string _aiModelVersion, uint256 _confidenceScore, string _eventType, string _clipCloudURI) external",
  "function verifyEvidence(bytes32 _videoHash) external view returns (bool exists, uint256 timestamp, uint256 loggedAt, string cameraId, bytes32 reportHash, bytes32 perceptualHash, string eventType, uint256 confidenceScore)",
  "function getEvidence(bytes32 _videoHash) external view returns (tuple(bytes32 videoHash, string cameraId, uint256 timestamp, address uploader, uint256 blockNumber, uint256 loggedAt, bytes32 reportHash, bytes32 perceptualHash, string aiModelVersion, uint256 confidenceScore, string eventType, string clipCloudURI))",
  "function getEvidenceCount() external view returns (uint256 count)",
  "function getEvidenceHashAtIndex(uint256 _index) external view returns (bytes32 hash)",
  "event EvidenceLogged(bytes32 indexed videoHash, string cameraId, uint256 timestamp, address indexed uploader, uint256 blockNumber, bytes32 reportHash, bytes32 perceptualHash, string eventType, uint256 confidenceScore)"
];

// Initialize Express
const app = express();

app.use(cors({
  origin: ['http://localhost:5173', 'http://127.0.0.1:5173'],
  methods: ['GET', 'POST'],
  credentials: true
}));
app.use(express.json());

// Configure video storage directory
const VIDEOS_DIR = path.resolve(__dirname, 'videos');
if (!fs.existsSync(VIDEOS_DIR)) {
  fs.mkdirSync(VIDEOS_DIR, { recursive: true });
}

const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, VIDEOS_DIR),
  filename: (req, file, cb) => {
    const timestamp = Date.now();
    const ext = path.extname(file.originalname) || '.mp4';
    cb(null, `evidence_${timestamp}${ext}`);
  }
});

const upload = multer({
  storage: storage,
  limits: { fileSize: 500 * 1024 * 1024 }
});

// Initialize SQLite database
const db = new Database(path.resolve(__dirname, DATABASE_PATH));
db.pragma('journal_mode = WAL');

db.exec(`
  CREATE TABLE IF NOT EXISTS evidence_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_hash TEXT NOT NULL UNIQUE,
    camera_id TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    file_path TEXT,
    file_size INTEGER,
    blockchain_tx TEXT,
    block_number INTEGER,
    uploader TEXT,
    detection_type TEXT,
    report_hash TEXT,
    perceptual_hash TEXT,
    ai_model_version TEXT,
    confidence_score INTEGER DEFAULT 0,
    event_type TEXT,
    clip_cloud_uri TEXT,
    status TEXT CHECK(status IN ('pending', 'confirmed', 'failed')) DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  );
`);

// Add new columns if they don't exist (for existing databases)
const newColumns = [
  'file_path TEXT', 'file_size INTEGER', 'detection_type TEXT',
  'report_hash TEXT', 'perceptual_hash TEXT', 'ai_model_version TEXT',
  'confidence_score INTEGER DEFAULT 0', 'event_type TEXT', 'clip_cloud_uri TEXT'
];
for (const col of newColumns) {
  try { db.exec(`ALTER TABLE evidence_log ADD COLUMN ${col}`); } catch (e) { /* exists */ }
}

// Create indexes after columns exist
db.exec(`
  CREATE INDEX IF NOT EXISTS idx_video_hash ON evidence_log(video_hash);
  CREATE INDEX IF NOT EXISTS idx_status ON evidence_log(status);
  CREATE INDEX IF NOT EXISTS idx_camera_id ON evidence_log(camera_id);
  CREATE INDEX IF NOT EXISTS idx_event_type ON evidence_log(event_type);
  CREATE INDEX IF NOT EXISTS idx_report_hash ON evidence_log(report_hash);
`);

// Prepared statements
const insertEvidence = db.prepare(`
  INSERT INTO evidence_log (video_hash, camera_id, timestamp, file_path, file_size, detection_type,
    report_hash, perceptual_hash, ai_model_version, confidence_score, event_type, clip_cloud_uri, status)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
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

function calculateHash(buffer) {
  return '0x' + crypto.createHash('sha256').update(buffer).digest('hex');
}

/**
 * Compute a perceptual hash approximation for video files.
 * Uses a different hashing strategy: samples evenly-spaced chunks from the file
 * and hashes them, providing content-locality sensitivity.
 */
function calculatePerceptualHash(buffer) {
  const sampleSize = 4096;
  const numSamples = 16;
  const step = Math.max(1, Math.floor(buffer.length / numSamples));
  const hash = crypto.createHash('sha256');

  for (let i = 0; i < numSamples; i++) {
    const offset = Math.min(i * step, buffer.length - sampleSize);
    if (offset >= 0 && offset + sampleSize <= buffer.length) {
      hash.update(buffer.slice(offset, offset + sampleSize));
    }
  }

  return '0x' + hash.digest('hex');
}

function isValidHash(hash) {
  return /^0x[a-fA-F0-9]{64}$/.test(hash);
}

/**
 * Compute Hamming distance between two 256-bit K2A hashes.
 * Returns count of differing bits (0 = identical content, higher = more modified).
 */
function k2aHammingDistance(hash1, hash2) {
  if (!hash1 || !hash2 || hash1 === ethers.ZeroHash || hash2 === ethers.ZeroHash) return null;
  const h1 = BigInt(hash1);
  const h2 = BigInt(hash2);
  const xor = h1 ^ h2;
  return xor.toString(2).split('').filter(b => b === '1').length;
}

/**
 * Copy clip to cloud storage
 */
function storeClip(sourcePath, videoHash) {
  try {
    const ext = path.extname(sourcePath) || '.mp4';
    const filename = `${videoHash.slice(2, 18)}_${Date.now()}${ext}`;
    const destPath = path.join(CLIPS_DIR, filename);
    fs.copyFileSync(sourcePath, destPath);
    return `local://cloud-storage/clips/${filename}`;
  } catch (e) {
    console.error('Failed to store clip:', e.message);
    return '';
  }
}

// API Routes

/**
 * POST /api/record
 */
app.post('/api/record', upload.single('video'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ success: false, error: 'No video file provided' });
    }

    const cameraId = req.body.cameraId;
    if (!cameraId || cameraId.trim() === '') {
      return res.status(400).json({ success: false, error: 'Camera ID is required' });
    }

    const detectionType = req.body.detectionType || 'manual';
    const filePath = req.file.path;
    const fileBuffer = fs.readFileSync(filePath);
    const videoHash = calculateHash(fileBuffer);
    const fileSize = req.file.size;
    const timestamp = Math.floor(Date.now() / 1000);

    const reportHash = req.body.reportHash || ethers.ZeroHash;
    const perceptualHash = req.body.perceptualHash && req.body.perceptualHash !== ethers.ZeroHash
      ? req.body.perceptualHash
      : calculatePerceptualHash(fileBuffer);
    const aiModelVersion = req.body.aiModelVersion || '';
    const confidenceScore = parseInt(req.body.confidenceScore) || 0;
    const eventType = req.body.eventType || detectionType;

    // Store clip to cloud storage
    const clipCloudURI = storeClip(filePath, videoHash);

    console.log(`Recording evidence: hash=${videoHash}, cameraId=${cameraId}, eventType=${eventType}`);

    const existing = getEvidenceByHash.get(videoHash);
    if (existing) {
      return res.status(409).json({
        success: false,
        error: 'Evidence with this hash already exists',
        existing: { videoHash: existing.video_hash, cameraId: existing.camera_id, status: existing.status }
      });
    }

    try {
      insertEvidence.run(
        videoHash, cameraId.trim(), timestamp, filePath, fileSize, detectionType,
        reportHash, perceptualHash, aiModelVersion, confidenceScore, eventType, clipCloudURI
      );
    } catch (dbError) {
      if (dbError.code === 'SQLITE_CONSTRAINT_UNIQUE') {
        fs.unlinkSync(filePath);
        return res.status(409).json({ success: false, error: 'Evidence already exists in database' });
      }
      throw dbError;
    }

    try {
      const tx = await contract.logEvidence(
        videoHash, cameraId.trim(), timestamp,
        reportHash, perceptualHash, aiModelVersion,
        confidenceScore, eventType, clipCloudURI
      );
      console.log(`Transaction submitted: ${tx.hash}`);

      const receipt = await tx.wait();
      console.log(`Transaction confirmed in block ${receipt.blockNumber}`);

      updateEvidenceConfirmed.run(receipt.hash, receipt.blockNumber, wallet.address, videoHash);

      return res.json({
        success: true,
        videoHash,
        transactionHash: receipt.hash,
        blockNumber: receipt.blockNumber,
        cameraId: cameraId.trim(),
        timestamp,
        filePath,
        fileSize,
        detectionType,
        reportHash,
        perceptualHash,
        aiModelVersion,
        confidenceScore,
        eventType,
        clipCloudURI
      });

    } catch (blockchainError) {
      console.error('Blockchain error:', blockchainError.message);
      updateEvidenceFailed.run(videoHash);

      if (blockchainError.message.includes('Evidence already exists')) {
        return res.status(409).json({ success: false, error: 'Evidence already exists on blockchain' });
      }
      return res.status(500).json({ success: false, error: 'Failed to record on blockchain: ' + blockchainError.message });
    }

  } catch (error) {
    console.error('Record error:', error);
    return res.status(500).json({ success: false, error: 'Internal server error: ' + error.message });
  }
});

/**
 * POST /api/verify
 */
app.post('/api/verify', upload.single('video'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ verified: false, error: 'No video file provided' });
    }

    const fileBuffer = fs.readFileSync(req.file.path);
    const videoHash = calculateHash(fileBuffer);
    // Compute K2A perceptual hash of the uploaded file for content comparison
    const uploadedPerceptualHash = calculatePerceptualHash(fileBuffer);
    console.log(`Verifying evidence: hash=${videoHash}`);

    fs.unlinkSync(req.file.path);

    const cachedEvidence = getEvidenceByHash.get(videoHash);

    try {
      const result = await contract.verifyEvidence(videoHash);

      if (result.exists) {
        const evidence = await contract.getEvidence(videoHash);

        // K2A perceptual hash comparison for content authenticity
        const storedPerceptualHash = evidence.perceptualHash;
        const hammingDist = k2aHammingDistance(storedPerceptualHash, uploadedPerceptualHash);
        const k2aVerdict = hammingDist === null
          ? 'no_perceptual_hash'
          : hammingDist <= 8 ? 'content_authentic' : 'content_modified';

        const responseData = {
          verified: true,
          source: cachedEvidence ? 'cache+blockchain' : 'blockchain',
          k2a_hamming_distance: hammingDist,
          k2a_verdict: k2aVerdict,
          evidence: {
            videoHash: evidence.videoHash,
            cameraId: evidence.cameraId,
            timestamp: Number(evidence.timestamp),
            uploader: evidence.uploader,
            blockNumber: Number(evidence.blockNumber),
            loggedAt: Number(evidence.loggedAt),
            reportHash: evidence.reportHash,
            perceptualHash: evidence.perceptualHash,
            aiModelVersion: evidence.aiModelVersion,
            confidenceScore: Number(evidence.confidenceScore),
            eventType: evidence.eventType,
            clipCloudURI: evidence.clipCloudURI
          }
        };

        if (!cachedEvidence) {
          try {
            insertEvidence.run(
              videoHash, evidence.cameraId, Number(evidence.timestamp),
              null, null, 'discovered',
              evidence.reportHash, evidence.perceptualHash,
              evidence.aiModelVersion, Number(evidence.confidenceScore),
              evidence.eventType, evidence.clipCloudURI
            );
            updateEvidenceConfirmed.run(null, Number(evidence.blockNumber), evidence.uploader, videoHash);
          } catch (e) { /* ignore if exists */ }
        }

        return res.json(responseData);
      } else {
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
            blockNumber: cachedEvidence.block_number,
            reportHash: cachedEvidence.report_hash,
            perceptualHash: cachedEvidence.perceptual_hash,
            aiModelVersion: cachedEvidence.ai_model_version,
            confidenceScore: cachedEvidence.confidence_score,
            eventType: cachedEvidence.event_type,
            clipCloudURI: cachedEvidence.clip_cloud_uri
          }
        });
      }

      return res.status(500).json({ verified: false, error: 'Blockchain verification failed: ' + blockchainError.message });
    }

  } catch (error) {
    console.error('Verify error:', error);
    return res.status(500).json({ verified: false, error: 'Internal server error: ' + error.message });
  }
});

/**
 * GET /api/logs
 */
app.get('/api/logs', async (req, res) => {
  try {
    const count = await contract.getEvidenceCount();
    const totalCount = Number(count);
    console.log(`Fetching ${totalCount} evidence records from blockchain`);

    const records = [];
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
          loggedAt: Number(evidence.loggedAt),
          reportHash: evidence.reportHash,
          perceptualHash: evidence.perceptualHash,
          aiModelVersion: evidence.aiModelVersion,
          confidenceScore: Number(evidence.confidenceScore),
          eventType: evidence.eventType,
          clipCloudURI: evidence.clipCloudURI
        });
      } catch (e) {
        console.error(`Error fetching evidence at index ${i}:`, e.message);
      }
    }

    records.sort((a, b) => b.timestamp - a.timestamp);

    return res.json({ success: true, count: records.length, records });

  } catch (error) {
    console.error('Logs error:', error);

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
          filePath: r.file_path,
          fileSize: r.file_size,
          detectionType: r.detection_type,
          reportHash: r.report_hash,
          perceptualHash: r.perceptual_hash,
          aiModelVersion: r.ai_model_version,
          confidenceScore: r.confidence_score,
          eventType: r.event_type,
          clipCloudURI: r.clip_cloud_uri,
          status: r.status
        }))
      });
    } catch (dbError) {
      return res.status(500).json({ success: false, error: 'Failed to fetch logs: ' + error.message });
    }
  }
});

/**
 * GET /api/health
 */
app.get('/api/health', async (req, res) => {
  try {
    const blockNumber = await provider.getBlockNumber();
    return res.json({ status: 'ok', blockchain: 'connected', blockNumber, contractAddress: CONTRACT_ADDRESS });
  } catch (error) {
    return res.json({ status: 'degraded', blockchain: 'disconnected', error: error.message });
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
