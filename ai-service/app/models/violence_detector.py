"""
Violence Detection Model
Uses motion analysis and deep learning for detecting violent activities
"""
import numpy as np
import cv2
from typing import Tuple, List, Optional
from dataclasses import dataclass
import threading


@dataclass
class DetectionResult:
    """Result of violence detection"""
    is_violent: bool
    confidence: float
    motion_score: float
    description: str


class ViolenceDetector:
    """
    Violence detection using motion analysis and optional deep learning.

    For demo purposes, uses motion-based detection which works well
    for detecting sudden aggressive movements, fighting, etc.
    """

    def __init__(
        self,
        threshold: float = 0.6,
        device: str = "cpu",
        use_deep_learning: bool = False,
        model_path: str = "yolov8n.pt"
    ):
        """
        Initialize the violence detector.

        Args:
            threshold: Detection threshold (0-1)
            device: 'cpu' or 'cuda'
            use_deep_learning: Whether to use YOLOv8-based detection
            model_path: YOLO model weights file (auto-downloaded if not present)
        """
        self.threshold = threshold
        self.device = device
        self.use_deep_learning = use_deep_learning
        self.model_path = model_path
        self._lock = threading.Lock()

        # Motion detection parameters
        self.motion_threshold = 50  # Pixel difference threshold
        self.motion_area_threshold = 0.1  # 10% of frame must have motion
        self.rapid_motion_multiplier = 2.0  # Multiplier for sudden motion

        # Frame history for motion analysis
        self._prev_frame: Optional[np.ndarray] = None
        self._motion_history: List[float] = []
        self._history_size = 30  # Keep last 30 motion scores

        # Deep learning model (optional)
        self._model = None
        self._transform = None

        if use_deep_learning:
            self._init_deep_model()

    def _init_deep_model(self):
        """Initialize YOLOv8 model for person/object detection."""
        try:
            from ultralytics import YOLO
            self._model = YOLO(self.model_path)  # auto-downloads yolov8n.pt
            print(f"YOLOv8 model loaded: {self.model_path}")
        except Exception as e:
            print(f"Could not load YOLO model: {e}")
            self.use_deep_learning = False

    def detect(self, frames: np.ndarray) -> DetectionResult:
        """
        Detect violence in a sequence of frames.

        Args:
            frames: numpy array of shape (N, H, W, C) or single frame (H, W, C)

        Returns:
            DetectionResult with detection status and confidence
        """
        with self._lock:
            # Handle single frame
            if len(frames.shape) == 3:
                frames = np.expand_dims(frames, axis=0)

            if len(frames) == 0:
                return DetectionResult(
                    is_violent=False,
                    confidence=0.0,
                    motion_score=0.0,
                    description="No frames to analyze"
                )

            # Analyze motion across frames
            motion_score = self._analyze_motion(frames)

            # Optional: deep learning analysis
            dl_score = 0.0
            if self.use_deep_learning and self._model is not None:
                dl_score = self._deep_learning_detect(frames[-1])

            # Combine scores
            if self.use_deep_learning:
                confidence = 0.4 * motion_score + 0.6 * dl_score
            else:
                confidence = motion_score

            is_violent = confidence >= self.threshold

            # Generate description
            if is_violent:
                if motion_score > 0.8:
                    description = "High-intensity motion detected - possible violent altercation"
                elif motion_score > 0.6:
                    description = "Aggressive motion pattern detected"
                else:
                    description = "Suspicious activity detected"
            else:
                description = "Normal activity"

            return DetectionResult(
                is_violent=is_violent,
                confidence=float(confidence),
                motion_score=float(motion_score),
                description=description
            )

    def _analyze_motion(self, frames: np.ndarray) -> float:
        """
        Analyze motion intensity across frames.
        High, sudden motion often indicates violence.

        Args:
            frames: Array of frames

        Returns:
            Motion score (0-1)
        """
        if len(frames) < 2:
            if self._prev_frame is None:
                self._prev_frame = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY)
                return 0.0
            frames = np.array([self._prev_frame, frames[0]])

        motion_scores = []

        for i in range(1, len(frames)):
            # Convert to grayscale
            if len(frames[i-1].shape) == 3:
                prev_gray = cv2.cvtColor(frames[i-1], cv2.COLOR_BGR2GRAY)
            else:
                prev_gray = frames[i-1]

            if len(frames[i].shape) == 3:
                curr_gray = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
            else:
                curr_gray = frames[i]

            # Calculate frame difference
            diff = cv2.absdiff(prev_gray, curr_gray)

            # Apply threshold
            _, thresh = cv2.threshold(diff, self.motion_threshold, 255, cv2.THRESH_BINARY)

            # Calculate motion area percentage
            motion_area = np.sum(thresh > 0) / thresh.size

            # Calculate motion intensity (mean of differences in motion areas)
            motion_intensity = np.mean(diff[thresh > 0]) / 255 if np.any(thresh > 0) else 0

            # Combined motion score
            frame_motion = min(1.0, motion_area * 5) * motion_intensity
            motion_scores.append(frame_motion)

        # Store last frame for next call
        self._prev_frame = frames[-1] if len(frames[-1].shape) == 2 else cv2.cvtColor(frames[-1], cv2.COLOR_BGR2GRAY)

        # Calculate current motion
        current_motion = np.mean(motion_scores) if motion_scores else 0.0

        # Update history
        self._motion_history.append(current_motion)
        if len(self._motion_history) > self._history_size:
            self._motion_history.pop(0)

        # Detect sudden motion spikes (characteristic of violence)
        if len(self._motion_history) >= 5:
            recent_avg = np.mean(self._motion_history[-5:])
            baseline_avg = np.mean(self._motion_history[:-5]) if len(self._motion_history) > 5 else 0.1

            # Spike detection
            if baseline_avg > 0 and recent_avg > baseline_avg * self.rapid_motion_multiplier:
                current_motion = min(1.0, current_motion * 1.5)

        return min(1.0, current_motion)

    def _deep_learning_detect(self, frame: np.ndarray) -> float:
        """Use YOLOv8 to detect persons/suspicious activity."""
        if self._model is None:
            return 0.0
        try:
            results = self._model(frame, verbose=False, device=self.device)[0]
            # Extract person detections (COCO class 0 = person)
            person_boxes = [b for b in results.boxes if int(b.cls) == 0 and float(b.conf) > 0.4]
            num_persons = len(person_boxes)
            if num_persons == 0:
                return 0.0
            avg_conf = sum(float(b.conf) for b in person_boxes) / num_persons
            crowd_score = min(1.0, num_persons / 4)  # 4+ persons = max crowd score
            proximity_score = self._calc_proximity(person_boxes)
            return min(1.0, avg_conf * 0.4 + crowd_score * 0.3 + proximity_score * 0.3)
        except Exception as e:
            print(f"YOLO detection error: {e}")
            return 0.0

    def _calc_proximity(self, boxes) -> float:
        """Score how close detected persons are to each other (0-1)."""
        if len(boxes) < 2:
            return 0.0
        centers = [(float(b.xywh[0][0]), float(b.xywh[0][1])) for b in boxes]
        min_dist = float('inf')
        for i in range(len(centers)):
            for j in range(i + 1, len(centers)):
                d = ((centers[i][0] - centers[j][0])**2 + (centers[i][1] - centers[j][1])**2)**0.5
                min_dist = min(min_dist, d)
        return max(0.0, 1.0 - min_dist / 300)  # <300px apart = high proximity

    def reset(self):
        """Reset the detector state."""
        with self._lock:
            self._prev_frame = None
            self._motion_history.clear()
