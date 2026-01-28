"""
Recording Manager
Handles saving incident videos and calculating hashes
Records entire event duration: pre-buffer + event + post-buffer
"""
import cv2
import hashlib
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Callable
from dataclasses import dataclass
import numpy as np

from .video_buffer import VideoBuffer, BufferedFrame
from ..config import settings


@dataclass
class IncidentRecording:
    """Represents a saved incident recording"""
    filepath: Path
    video_hash: str
    camera_id: str
    timestamp: float
    duration: float
    frame_count: int
    detection_type: str
    confidence: float


class RecordingManager:
    """
    Manages incident recording from video buffer.
    Records: pre-buffer (5s) + entire event duration + post-buffer (5s)
    """

    def __init__(
        self,
        buffer: VideoBuffer,
        recordings_dir: Path = None,
        post_incident_duration: int = 5,
        fps: int = 30,
        on_recording_complete: Optional[Callable[[IncidentRecording], None]] = None
    ):
        """
        Initialize the recording manager.

        Args:
            buffer: Video buffer to record from
            recordings_dir: Directory to save recordings
            post_incident_duration: Seconds to record after event ends
            fps: Frames per second for saved video
            on_recording_complete: Callback when recording is saved
        """
        self.buffer = buffer
        self.recordings_dir = recordings_dir or settings.recordings_dir
        self.post_incident_duration = post_incident_duration
        self.fps = fps
        self.on_recording_complete = on_recording_complete

        self._lock = threading.Lock()
        self._is_recording = False
        self._event_active = False  # True while event is ongoing
        self._recording_thread: Optional[threading.Thread] = None
        self._event_frames: List[np.ndarray] = []  # Frames during event
        self._pre_frames: List[np.ndarray] = []  # Pre-event buffer frames
        self._current_detection_type = ""
        self._current_confidence = 0.0
        self._last_detection_time = 0.0

        # Ensure recordings directory exists
        self.recordings_dir.mkdir(parents=True, exist_ok=True)

    def start_event(
        self,
        detection_type: str = "violence",
        confidence: float = 0.0
    ) -> bool:
        """
        Start recording an event. Call this when detection first triggers.
        Captures pre-buffer and starts collecting event frames.

        Args:
            detection_type: Type of detection
            confidence: Detection confidence score

        Returns:
            True if event started, False if already recording
        """
        with self._lock:
            if self._is_recording:
                # Already recording - just update the last detection time
                self._last_detection_time = time.time()
                self._current_confidence = max(self._current_confidence, confidence)
                return False

            self._is_recording = True
            self._event_active = True
            self._current_detection_type = detection_type
            self._current_confidence = confidence
            self._last_detection_time = time.time()
            self._event_frames = []

            # Capture pre-event buffer immediately
            pre_buffer = self.buffer.get_frames()
            self._pre_frames = [f.frame.copy() for f in pre_buffer]

        print(f"Event started: {detection_type} (confidence: {confidence:.2f})")
        print(f"Pre-buffer captured: {len(self._pre_frames)} frames")

        # Start the recording worker
        self._recording_thread = threading.Thread(
            target=self._recording_worker,
            daemon=True
        )
        self._recording_thread.start()

        return True

    def continue_event(self, confidence: float = 0.0):
        """
        Call this while the event is still ongoing (detection still active).
        Extends the recording.
        """
        with self._lock:
            if self._is_recording:
                self._last_detection_time = time.time()
                self._current_confidence = max(self._current_confidence, confidence)
                self._event_active = True

    def add_frame(self, frame: np.ndarray):
        """
        Add a frame during the event.
        Called for every frame while recording is active.
        """
        if self._is_recording:
            with self._lock:
                self._event_frames.append(frame.copy())

    def _recording_worker(self):
        """Background worker that waits for event to end, then saves."""
        try:
            # Wait for event to end (no detection for post_incident_duration)
            while True:
                time.sleep(0.1)

                with self._lock:
                    time_since_last = time.time() - self._last_detection_time

                    # Event ended if no detection for post_incident_duration
                    if time_since_last >= self.post_incident_duration:
                        self._event_active = False
                        break

            # Collect final post-event frames (already included in event_frames)
            # Wait a tiny bit more to ensure we have post-buffer
            time.sleep(0.5)

            with self._lock:
                all_frames = self._pre_frames + self._event_frames

            if len(all_frames) < 10:
                print("Not enough frames to save recording")
                return

            # Generate filename
            timestamp = datetime.now()
            filename = f"{self._current_detection_type}_{timestamp.strftime('%Y%m%d_%H%M%S')}.mp4"
            filepath = self.recordings_dir / filename

            # Save video
            self._save_video(all_frames, filepath)

            # Calculate hash
            video_hash = self._calculate_hash(filepath)

            # Create recording info
            recording = IncidentRecording(
                filepath=filepath,
                video_hash=video_hash,
                camera_id=settings.camera_id,
                timestamp=timestamp.timestamp(),
                duration=len(all_frames) / self.fps,
                frame_count=len(all_frames),
                detection_type=self._current_detection_type,
                confidence=self._current_confidence
            )

            print(f"Recording saved: {filepath}")
            print(f"Hash: {video_hash}")
            print(f"Duration: {recording.duration:.1f}s, Frames: {recording.frame_count}")

            # Callback
            if self.on_recording_complete:
                self.on_recording_complete(recording)

        except Exception as e:
            print(f"Recording error: {e}")

        finally:
            with self._lock:
                self._is_recording = False
                self._event_active = False
                self._event_frames = []
                self._pre_frames = []

    @property
    def is_recording(self) -> bool:
        """Check if currently recording an event."""
        return self._is_recording

    @property
    def is_event_active(self) -> bool:
        """Check if event is still ongoing."""
        return self._event_active

    def trigger_test_recording(self) -> bool:
        """Trigger a manual test recording (for demo purposes)."""
        if self._is_recording:
            return False

        # Start a short test event
        self.start_event(detection_type="manual_test", confidence=1.0)

        # Auto-end after 2 seconds
        def end_test():
            time.sleep(2)
            # Don't call continue_event - let it naturally end

        threading.Thread(target=end_test, daemon=True).start()
        return True

    def _save_video(self, frames: List[np.ndarray], filepath: Path):
        """
        Save frames as MP4 video.

        Args:
            frames: List of frames (numpy arrays)
            filepath: Output file path
        """
        if not frames:
            return

        height, width = frames[0].shape[:2]

        # Use mp4v codec for compatibility
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(
            str(filepath),
            fourcc,
            self.fps,
            (width, height)
        )

        try:
            for frame in frames:
                writer.write(frame)
        finally:
            writer.release()

    def _calculate_hash(self, filepath: Path) -> str:
        """
        Calculate SHA-256 hash of video file.

        Args:
            filepath: Path to video file

        Returns:
            Hash string with 0x prefix (for blockchain compatibility)
        """
        sha256_hash = hashlib.sha256()

        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)

        return "0x" + sha256_hash.hexdigest()

    @property
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._is_recording

    def cleanup_old_recordings(self, max_age_days: int = None):
        """
        Remove recordings older than max_age_days.

        Args:
            max_age_days: Maximum age in days (default from settings)
        """
        max_age_days = max_age_days or settings.retention_days
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)

        for filepath in self.recordings_dir.glob("*.mp4"):
            if filepath.stat().st_mtime < cutoff_time:
                filepath.unlink()
                print(f"Deleted old recording: {filepath.name}")
