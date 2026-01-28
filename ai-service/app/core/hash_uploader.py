"""
Hash Uploader
Sends incident recordings to backend API for blockchain storage
"""
import asyncio
import httpx
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from .recording_manager import IncidentRecording
from ..config import settings


@dataclass
class UploadResult:
    """Result of uploading to backend"""
    success: bool
    video_hash: str
    transaction_hash: Optional[str] = None
    block_number: Optional[int] = None
    error: Optional[str] = None


class HashUploader:
    """
    Uploads incident recordings to the backend API.
    The backend handles blockchain storage on Polygon.
    """

    def __init__(
        self,
        backend_url: str = None,
        timeout: int = None
    ):
        """
        Initialize the uploader.

        Args:
            backend_url: Backend API base URL
            timeout: Request timeout in seconds
        """
        self.backend_url = backend_url or settings.backend_url
        self.timeout = timeout or settings.backend_timeout_seconds

    async def upload_recording(self, recording: IncidentRecording) -> UploadResult:
        """
        Upload an incident recording to the backend.

        Args:
            recording: IncidentRecording object with file path and metadata

        Returns:
            UploadResult with blockchain transaction details
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Read video file
                with open(recording.filepath, "rb") as f:
                    video_data = f.read()

                # Prepare multipart form data
                files = {
                    "video": (recording.filepath.name, video_data, "video/mp4")
                }
                data = {
                    "cameraId": recording.camera_id
                }

                # POST to backend
                response = await client.post(
                    f"{self.backend_url}/api/record",
                    files=files,
                    data=data
                )

                if response.status_code == 200:
                    result = response.json()
                    return UploadResult(
                        success=True,
                        video_hash=result.get("videoHash", recording.video_hash),
                        transaction_hash=result.get("transactionHash"),
                        block_number=result.get("blockNumber")
                    )
                else:
                    error_msg = response.text
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("error", error_msg)
                    except:
                        pass

                    return UploadResult(
                        success=False,
                        video_hash=recording.video_hash,
                        error=f"Backend error ({response.status_code}): {error_msg}"
                    )

        except httpx.TimeoutException:
            return UploadResult(
                success=False,
                video_hash=recording.video_hash,
                error="Request timeout - backend may be slow"
            )
        except httpx.ConnectError:
            return UploadResult(
                success=False,
                video_hash=recording.video_hash,
                error="Cannot connect to backend - is it running?"
            )
        except Exception as e:
            return UploadResult(
                success=False,
                video_hash=recording.video_hash,
                error=str(e)
            )

    def upload_recording_sync(self, recording: IncidentRecording) -> UploadResult:
        """
        Synchronous wrapper for upload_recording.

        Args:
            recording: IncidentRecording object

        Returns:
            UploadResult
        """
        return asyncio.run(self.upload_recording(recording))

    async def verify_hash(self, video_hash: str) -> dict:
        """
        Verify a hash exists on blockchain via backend.

        Args:
            video_hash: SHA-256 hash with 0x prefix

        Returns:
            Verification result from backend
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.backend_url}/api/verify",
                    json={"videoHash": video_hash}
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    return {"verified": False, "error": response.text}

        except Exception as e:
            return {"verified": False, "error": str(e)}

    async def health_check(self) -> bool:
        """
        Check if backend is reachable.

        Returns:
            True if backend is healthy
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.backend_url}/api/logs")
                return response.status_code == 200
        except:
            return False
