"""
Circular video buffer for storing rolling footage
Maintains the last N seconds of video frames for incident capture
"""
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import List, Tuple, Optional
import numpy as np


@dataclass
class BufferedFrame:
    """A single frame with metadata"""
    frame: np.ndarray
    timestamp: float
    frame_number: int


class VideoBuffer:
    """
    Thread-safe circular buffer for video frames.
    Automatically maintains a rolling window of the last N seconds.
    """

    def __init__(self, duration_seconds: int = 60, fps: int = 30):
        """
        Initialize the video buffer.

        Args:
            duration_seconds: How many seconds of video to keep
            fps: Expected frames per second (used to calculate capacity)
        """
        self.duration_seconds = duration_seconds
        self.fps = fps
        self.max_frames = duration_seconds * fps

        self._buffer: deque = deque(maxlen=self.max_frames)
        self._lock = threading.RLock()
        self._frame_count = 0
        self._start_time = time.time()

    def add_frame(self, frame: np.ndarray) -> None:
        """
        Add a frame to the buffer. Old frames are automatically evicted.

        Args:
            frame: numpy array representing the video frame (BGR format)
        """
        with self._lock:
            buffered = BufferedFrame(
                frame=frame.copy(),  # Copy to avoid reference issues
                timestamp=time.time(),
                frame_number=self._frame_count
            )
            self._buffer.append(buffered)
            self._frame_count += 1

    def get_frames(self, seconds: Optional[int] = None) -> List[BufferedFrame]:
        """
        Get frames from the buffer.

        Args:
            seconds: Number of seconds to retrieve (None = all frames)

        Returns:
            List of BufferedFrame objects, oldest first
        """
        with self._lock:
            if seconds is None:
                return list(self._buffer)

            # Get frames from the last N seconds
            cutoff_time = time.time() - seconds
            return [f for f in self._buffer if f.timestamp >= cutoff_time]

    def get_frames_as_array(self, seconds: Optional[int] = None) -> np.ndarray:
        """
        Get frames as a numpy array.

        Args:
            seconds: Number of seconds to retrieve

        Returns:
            numpy array of shape (N, H, W, C)
        """
        frames = self.get_frames(seconds)
        if not frames:
            return np.array([])
        return np.stack([f.frame for f in frames])

    def get_recent_frames(self, count: int) -> List[BufferedFrame]:
        """
        Get the N most recent frames.

        Args:
            count: Number of frames to retrieve

        Returns:
            List of BufferedFrame objects
        """
        with self._lock:
            if count >= len(self._buffer):
                return list(self._buffer)
            return list(self._buffer)[-count:]

    def clear(self) -> None:
        """Clear all frames from the buffer."""
        with self._lock:
            self._buffer.clear()
            self._frame_count = 0

    @property
    def size(self) -> int:
        """Current number of frames in buffer."""
        with self._lock:
            return len(self._buffer)

    @property
    def duration(self) -> float:
        """Current duration of buffered video in seconds."""
        with self._lock:
            if len(self._buffer) < 2:
                return 0.0
            return self._buffer[-1].timestamp - self._buffer[0].timestamp

    @property
    def is_full(self) -> bool:
        """Check if buffer has reached capacity."""
        with self._lock:
            return len(self._buffer) >= self.max_frames

    def __len__(self) -> int:
        return self.size
