"""
Forensic Report Generator
Uses Gemini VLM to analyze incident video frames and generate structured forensic reports.
Report hashes are stored on-chain for provenance verification.
"""
import base64
import cv2
import hashlib
import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

try:
    from google import genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


@dataclass
class ForensicReport:
    """Structured forensic report for an incident"""
    video_hash: str
    camera_id: str
    timestamp: float
    event_type: str
    confidence: float
    summary: str = ""
    detailed_description: str = ""
    identified_objects: List[str] = field(default_factory=list)
    severity: str = "unknown"  # low, medium, high, critical
    recommended_actions: List[str] = field(default_factory=list)
    ai_model_version: str = ""
    report_hash: str = ""
    generated_at: str = ""

    def to_dict(self):
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class ForensicReportGenerator:
    """
    Generates forensic reports using Gemini Vision Language Model.
    Rate-limited to 14 req/min for free tier safety.
    """

    STRUCTURED_PROMPT = """You are a forensic video analyst. Analyze these CCTV surveillance frames and provide a structured forensic report.

Context:
- Camera ID: {camera_id}
- Detected Event Type: {event_type}
- Detection Confidence: {confidence:.1%}
- Timestamp: {timestamp}

Respond ONLY with valid JSON in this exact format:
{{
    "summary": "One-sentence summary of the incident",
    "detailed_description": "2-3 sentence detailed description of what is observed in the frames",
    "identified_objects": ["list", "of", "key", "objects", "or", "persons", "observed"],
    "severity": "low|medium|high|critical",
    "recommended_actions": ["list", "of", "recommended", "follow-up", "actions"]
}}"""

    def __init__(
        self,
        api_key: str = None,
        model_name: str = None,
        max_frames: int = 10,
        rate_limit_rpm: int = 14
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        self.max_frames = max_frames
        self.rate_limit_rpm = rate_limit_rpm
        self._last_request_time = 0
        self._min_interval = 60.0 / rate_limit_rpm

        self.client = None
        if HAS_GENAI and self.api_key:
            self.client = genai.Client(api_key=self.api_key)

    @property
    def is_available(self) -> bool:
        return self.client is not None

    def extract_frames(self, video_path: str, max_frames: int = None) -> List[bytes]:
        """Extract evenly-spaced frames from video as JPEG bytes."""
        max_frames = max_frames or self.max_frames
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            total = 300  # fallback

        indices = [int(i * total / max_frames) for i in range(max_frames)]
        frames = []

        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                frames.append(buf.tobytes())

        cap.release()
        return frames

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def analyze_frames(self, frames: List[bytes], context: dict) -> dict:
        """Send frames to Gemini and parse structured response."""
        if not self.is_available:
            return self._fallback_analysis(context)

        self._rate_limit()

        prompt = self.STRUCTURED_PROMPT.format(**context)

        # Build content parts: prompt + images
        content_parts = [genai.types.Part.from_text(text=prompt)]
        for frame_bytes in frames:
            content_parts.append(genai.types.Part.from_bytes(
                data=frame_bytes,
                mime_type="image/jpeg"
            ))

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=content_parts
            )
            text = response.text.strip()

            # Extract JSON from response (handle markdown code blocks)
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            return json.loads(text)

        except Exception as e:
            print(f"Gemini analysis failed: {e}")
            return self._fallback_analysis(context)

    def _fallback_analysis(self, context: dict) -> dict:
        """Generate basic report from detection metadata when Gemini is unavailable."""
        return {
            "summary": f"{context['event_type']} detected by camera {context['camera_id']}",
            "detailed_description": f"Automated detection triggered with {context['confidence']:.1%} confidence. Manual review recommended.",
            "identified_objects": ["motion", "anomaly"],
            "severity": "medium" if context['confidence'] > 0.7 else "low",
            "recommended_actions": ["Review footage manually", "Check camera feed"]
        }

    def generate_report(
        self,
        video_path: str,
        video_hash: str,
        camera_id: str,
        timestamp: float,
        event_type: str,
        confidence: float
    ) -> ForensicReport:
        """Full pipeline: extract frames, analyze, hash report, return."""
        context = {
            "camera_id": camera_id,
            "event_type": event_type,
            "confidence": confidence,
            "timestamp": datetime.fromtimestamp(timestamp).isoformat()
        }

        frames = self.extract_frames(video_path)
        analysis = self.analyze_frames(frames, context)

        report = ForensicReport(
            video_hash=video_hash,
            camera_id=camera_id,
            timestamp=timestamp,
            event_type=event_type,
            confidence=confidence,
            summary=analysis.get("summary", ""),
            detailed_description=analysis.get("detailed_description", ""),
            identified_objects=analysis.get("identified_objects", []),
            severity=analysis.get("severity", "unknown"),
            recommended_actions=analysis.get("recommended_actions", []),
            ai_model_version=self.model_name if self.is_available else "fallback",
            generated_at=datetime.now().isoformat()
        )

        # Compute report hash
        report_json = report.to_json()
        report.report_hash = "0x" + hashlib.sha256(report_json.encode()).hexdigest()

        return report

    def save_report(self, report: ForensicReport, output_dir: str) -> Path:
        """Save report as JSON to output directory."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        filename = f"report_{report.video_hash[2:18]}_{int(report.timestamp)}.json"
        filepath = output_path / filename

        with open(filepath, 'w') as f:
            f.write(report.to_json())

        return filepath
