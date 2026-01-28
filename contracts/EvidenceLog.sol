// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/**
 * @title EvidenceLog
 * @dev Stores cryptographic hashes of CCTV video footage for tamper-proof verification
 * @notice This contract provides immutable evidence logging for surveillance systems
 */
contract EvidenceLog {
    struct Evidence {
        bytes32 videoHash;      // SHA-256 hash of the video file
        string cameraId;        // Unique identifier for the camera
        uint256 timestamp;      // Unix timestamp when footage was hashed (real-time hashing)
        address uploader;       // Address that logged the evidence
        uint256 blockNumber;    // Block number when evidence was logged
        uint256 loggedAt;       // Block timestamp when logged on-chain
    }

    // Mapping from video hash to Evidence struct
    mapping(bytes32 => Evidence) public evidenceRecords;

    // Array to track all evidence hashes for enumeration
    bytes32[] public evidenceHashes;

    // Events
    event EvidenceLogged(
        bytes32 indexed videoHash,
        string cameraId,
        uint256 timestamp,
        address indexed uploader,
        uint256 blockNumber
    );

    /**
     * @dev Logs a new piece of evidence on-chain
     * @param _videoHash SHA-256 hash of the video file (must be unique)
     * @param _cameraId Identifier of the camera that recorded the footage
     * @param _timestamp Unix timestamp when the footage was hashed (real-time)
     */
    function logEvidence(
        bytes32 _videoHash,
        string calldata _cameraId,
        uint256 _timestamp
    ) external {
        // Ensure hash is not empty
        require(_videoHash != bytes32(0), "Video hash cannot be empty");

        // Ensure this hash hasn't been logged before (prevents duplicates)
        require(
            evidenceRecords[_videoHash].videoHash == bytes32(0),
            "Evidence already exists"
        );

        // Ensure camera ID is provided
        require(bytes(_cameraId).length > 0, "Camera ID cannot be empty");

        // Ensure timestamp is valid (positive value)
        require(_timestamp > 0, "Timestamp must be positive");

        // Create and store the evidence record
        evidenceRecords[_videoHash] = Evidence({
            videoHash: _videoHash,
            cameraId: _cameraId,
            timestamp: _timestamp,
            uploader: msg.sender,
            blockNumber: block.number,
            loggedAt: block.timestamp
        });

        // Add hash to the array for enumeration
        evidenceHashes.push(_videoHash);

        // Emit event for off-chain tracking
        emit EvidenceLogged(
            _videoHash,
            _cameraId,
            _timestamp,
            msg.sender,
            block.number
        );
    }

    /**
     * @dev Verifies if a video hash exists on-chain and returns timing details
     * @param _videoHash SHA-256 hash to verify
     * @return exists True if the hash exists, false otherwise
     * @return timestamp Unix timestamp when the footage was hashed (real-time)
     * @return loggedAt Block timestamp when evidence was logged on-chain
     * @return cameraId The camera that recorded the footage
     */
    function verifyEvidence(bytes32 _videoHash) external view returns (
        bool exists,
        uint256 timestamp,
        uint256 loggedAt,
        string memory cameraId
    ) {
        Evidence memory evidence = evidenceRecords[_videoHash];
        if (evidence.videoHash == bytes32(0)) {
            return (false, 0, 0, "");
        }
        return (true, evidence.timestamp, evidence.loggedAt, evidence.cameraId);
    }

    /**
     * @dev Retrieves the full evidence record for a given hash
     * @param _videoHash SHA-256 hash to look up
     * @return evidence The complete Evidence struct
     */
    function getEvidence(bytes32 _videoHash) external view returns (Evidence memory evidence) {
        require(
            evidenceRecords[_videoHash].videoHash != bytes32(0),
            "Evidence does not exist"
        );
        return evidenceRecords[_videoHash];
    }

    /**
     * @dev Returns the total number of evidence records
     * @return count Total number of logged evidence
     */
    function getEvidenceCount() external view returns (uint256 count) {
        return evidenceHashes.length;
    }

    /**
     * @dev Returns evidence hash at a specific index
     * @param _index Index in the evidenceHashes array
     * @return hash The video hash at that index
     */
    function getEvidenceHashAtIndex(uint256 _index) external view returns (bytes32 hash) {
        require(_index < evidenceHashes.length, "Index out of bounds");
        return evidenceHashes[_index];
    }
}
