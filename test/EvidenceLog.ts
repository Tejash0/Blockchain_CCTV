import { expect } from "chai";
import { ethers } from "hardhat";
import { EvidenceLog } from "../typechain-types";
import { HardhatEthersSigner } from "@nomicfoundation/hardhat-ethers/signers";

describe("EvidenceLog", function () {
  let evidenceLog: EvidenceLog;
  let owner: HardhatEthersSigner;
  let addr1: HardhatEthersSigner;

  // Sample test data
  const sampleHash = ethers.keccak256(ethers.toUtf8Bytes("sample_video_content"));
  const sampleCameraId = "CAM-001";
  const sampleTimestamp = Math.floor(Date.now() / 1000) - 3600; // 1 hour ago

  beforeEach(async function () {
    [owner, addr1] = await ethers.getSigners();

    const EvidenceLogFactory = await ethers.getContractFactory("EvidenceLog");
    evidenceLog = await EvidenceLogFactory.deploy();
    await evidenceLog.waitForDeployment();
  });

  describe("Deployment", function () {
    it("Should deploy successfully", async function () {
      expect(await evidenceLog.getAddress()).to.be.properAddress;
    });

    it("Should start with zero evidence count", async function () {
      expect(await evidenceLog.getEvidenceCount()).to.equal(0);
    });
  });

  describe("logEvidence", function () {
    it("Should log evidence successfully", async function () {
      await expect(
        evidenceLog.logEvidence(sampleHash, sampleCameraId, sampleTimestamp)
      )
        .to.emit(evidenceLog, "EvidenceLogged")
        .withArgs(
          sampleHash,
          sampleCameraId,
          sampleTimestamp,
          owner.address,
          await ethers.provider.getBlockNumber() + 1
        );

      expect(await evidenceLog.getEvidenceCount()).to.equal(1);
    });

    it("Should store correct evidence data", async function () {
      await evidenceLog.logEvidence(sampleHash, sampleCameraId, sampleTimestamp);

      const evidence = await evidenceLog.getEvidence(sampleHash);
      expect(evidence.videoHash).to.equal(sampleHash);
      expect(evidence.cameraId).to.equal(sampleCameraId);
      expect(evidence.timestamp).to.equal(sampleTimestamp);
      expect(evidence.uploader).to.equal(owner.address);
    });

    it("Should prevent duplicate hashes", async function () {
      await evidenceLog.logEvidence(sampleHash, sampleCameraId, sampleTimestamp);

      await expect(
        evidenceLog.logEvidence(sampleHash, "CAM-002", sampleTimestamp)
      ).to.be.revertedWith("Evidence already exists");
    });

    it("Should reject empty video hash", async function () {
      const emptyHash = ethers.ZeroHash;

      await expect(
        evidenceLog.logEvidence(emptyHash, sampleCameraId, sampleTimestamp)
      ).to.be.revertedWith("Video hash cannot be empty");
    });

    it("Should reject empty camera ID", async function () {
      await expect(
        evidenceLog.logEvidence(sampleHash, "", sampleTimestamp)
      ).to.be.revertedWith("Camera ID cannot be empty");
    });

    it("Should reject future timestamps", async function () {
      const futureTimestamp = Math.floor(Date.now() / 1000) + 86400; // 1 day in future

      await expect(
        evidenceLog.logEvidence(sampleHash, sampleCameraId, futureTimestamp)
      ).to.be.revertedWith("Timestamp cannot be in the future");
    });

    it("Should allow different users to log evidence", async function () {
      const hash1 = ethers.keccak256(ethers.toUtf8Bytes("video1"));
      const hash2 = ethers.keccak256(ethers.toUtf8Bytes("video2"));

      await evidenceLog.connect(owner).logEvidence(hash1, "CAM-001", sampleTimestamp);
      await evidenceLog.connect(addr1).logEvidence(hash2, "CAM-002", sampleTimestamp);

      const evidence1 = await evidenceLog.getEvidence(hash1);
      const evidence2 = await evidenceLog.getEvidence(hash2);

      expect(evidence1.uploader).to.equal(owner.address);
      expect(evidence2.uploader).to.equal(addr1.address);
    });
  });

  describe("verifyEvidence", function () {
    it("Should return true for existing evidence", async function () {
      await evidenceLog.logEvidence(sampleHash, sampleCameraId, sampleTimestamp);

      expect(await evidenceLog.verifyEvidence(sampleHash)).to.equal(true);
    });

    it("Should return false for non-existent evidence", async function () {
      const nonExistentHash = ethers.keccak256(ethers.toUtf8Bytes("non_existent"));

      expect(await evidenceLog.verifyEvidence(nonExistentHash)).to.equal(false);
    });
  });

  describe("getEvidence", function () {
    it("Should return complete evidence record", async function () {
      const tx = await evidenceLog.logEvidence(sampleHash, sampleCameraId, sampleTimestamp);
      const receipt = await tx.wait();
      const block = await ethers.provider.getBlock(receipt!.blockNumber);

      const evidence = await evidenceLog.getEvidence(sampleHash);

      expect(evidence.videoHash).to.equal(sampleHash);
      expect(evidence.cameraId).to.equal(sampleCameraId);
      expect(evidence.timestamp).to.equal(sampleTimestamp);
      expect(evidence.uploader).to.equal(owner.address);
      expect(evidence.blockNumber).to.equal(receipt!.blockNumber);
      expect(evidence.loggedAt).to.equal(block!.timestamp);
    });

    it("Should revert for non-existent evidence", async function () {
      const nonExistentHash = ethers.keccak256(ethers.toUtf8Bytes("non_existent"));

      await expect(
        evidenceLog.getEvidence(nonExistentHash)
      ).to.be.revertedWith("Evidence does not exist");
    });
  });

  describe("Evidence enumeration", function () {
    it("Should track evidence count correctly", async function () {
      expect(await evidenceLog.getEvidenceCount()).to.equal(0);

      await evidenceLog.logEvidence(
        ethers.keccak256(ethers.toUtf8Bytes("video1")),
        "CAM-001",
        sampleTimestamp
      );
      expect(await evidenceLog.getEvidenceCount()).to.equal(1);

      await evidenceLog.logEvidence(
        ethers.keccak256(ethers.toUtf8Bytes("video2")),
        "CAM-002",
        sampleTimestamp
      );
      expect(await evidenceLog.getEvidenceCount()).to.equal(2);
    });

    it("Should return correct hash at index", async function () {
      const hash1 = ethers.keccak256(ethers.toUtf8Bytes("video1"));
      const hash2 = ethers.keccak256(ethers.toUtf8Bytes("video2"));

      await evidenceLog.logEvidence(hash1, "CAM-001", sampleTimestamp);
      await evidenceLog.logEvidence(hash2, "CAM-002", sampleTimestamp);

      expect(await evidenceLog.getEvidenceHashAtIndex(0)).to.equal(hash1);
      expect(await evidenceLog.getEvidenceHashAtIndex(1)).to.equal(hash2);
    });

    it("Should revert for out of bounds index", async function () {
      await expect(
        evidenceLog.getEvidenceHashAtIndex(0)
      ).to.be.revertedWith("Index out of bounds");
    });
  });
});
