"""
Video Stream Processor
Handles video input from webcam, file, or RTSP stream
"""
import cv2
import threading
import time
from typing import Callable, Optional
import numpy as np
from ..config import settings


class StreamProcessor:
    """
    Processes video streams from various sources.
    Feeds frames to buffer and detection pipeline.
    """

    def __init__(
        self,
        source: str = "0",
        target_fps: int = 30,
        analysis_fps: int = 5,
        on_frame: Optional[Callable[[np.ndarray], None]] = None,
        on_analysis_frame: Optional[Callable[[np.ndarray], None]] = None
    ):
        """
        Initialize the stream processor.

        Args:
            source: Video source (0 for webcam, path for file, URL for RTSP)
            target_fps: Target FPS for frame capture
            analysis_fps: FPS for analysis frames (lower for efficiency)
            on_frame: Callback for every frame (for buffer)
            on_analysis_frame: Callback for analysis frames (for detection)
        """
        self.source = source
        self.target_fps = target_fps
        self.analysis_fps = analysis_fps
        self.on_frame = on_frame
        self.on_analysis_frame = on_analysis_frame

        self._capture: Optional[cv2.VideoCapture] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Stats
        self.frame_count = 0
        self.actual_fps = 0.0
        self.last_frame: Optional[np.ndarray] = None
        self._fps_start_time = time.time()
        self._fps_frame_count = 0

    def start(self) -> bool:
        """
        Start processing the video stream.

        Returns:
            True if started successfully, False otherwise
        """
        with self._lock:
            if self._running:
                return True

            # Parse source
            if self.source.isdigit():
                source = int(self.source)
            else:
                source = self.source

            # Open video capture
            self._capture = cv2.VideoCapture(source)

            if not self._capture.isOpened():
                print(f"Failed to open video source: {self.source}")
                return False

            # Get source properties
            src_fps = self._capture.get(cv2.CAP_PROP_FPS)
            if src_fps > 0:
                self.target_fps = min(self.target_fps, int(src_fps))

            self._running = True
            self._thread = threading.Thread(target=self._process_loop, daemon=True)
            self._thread.start()

            print(f"Stream started: {self.source} @ {self.target_fps} FPS")
            return True

    def stop(self):
        """Stop processing the video stream."""
        with self._lock:
            self._running = False

        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        if self._capture is not None:
            self._capture.release()
            self._capture = None

        print("Stream stopped")

    def _process_loop(self):
        """Main processing loop."""
        frame_interval = 1.0 / self.target_fps
        analysis_interval = 1.0 / self.analysis_fps
        last_analysis_time = 0

        while self._running:
            loop_start = time.time()

            # Read frame
            ret, frame = self._capture.read()

            if not ret:
                # End of video file or stream error
                if isinstance(self.source, str) and not self.source.isdigit():
                    # Video file ended - loop or stop
                    self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    # Stream error - try to reconnect
                    print("Stream error, attempting reconnect...")
                    time.sleep(1)
                    self._reconnect()
                    continue

            self.frame_count += 1
            self.last_frame = frame

            # Update FPS calculation
            self._fps_frame_count += 1
            elapsed = time.time() - self._fps_start_time
            if elapsed >= 1.0:
                self.actual_fps = self._fps_frame_count / elapsed
                self._fps_frame_count = 0
                self._fps_start_time = time.time()

            # Callback for every frame (buffer)
            if self.on_frame is not None:
                try:
                    self.on_frame(frame)
                except Exception as e:
                    print(f"Frame callback error: {e}")

            # Callback for analysis frames (detection)
            current_time = time.time()
            if current_time - last_analysis_time >= analysis_interval:
                if self.on_analysis_frame is not None:
                    try:
                        self.on_analysis_frame(frame)
                    except Exception as e:
                        print(f"Analysis callback error: {e}")
                last_analysis_time = current_time

            # Frame rate limiting
            elapsed = time.time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _reconnect(self):
        """Attempt to reconnect to the video source."""
        if self._capture is not None:
            self._capture.release()

        if self.source.isdigit():
            source = int(self.source)
        else:
            source = self.source

        self._capture = cv2.VideoCapture(source)

        if self._capture.isOpened():
            print("Reconnected to stream")
        else:
            print("Reconnection failed")

    def get_frame(self) -> Optional[np.ndarray]:
        """Get the most recent frame."""
        return self.last_frame

    @property
    def is_running(self) -> bool:
        """Check if the stream is running."""
        return self._running

    @property
    def resolution(self) -> tuple:
        """Get current frame resolution."""
        if self._capture is None:
            return (0, 0)
        width = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return (width, height)
