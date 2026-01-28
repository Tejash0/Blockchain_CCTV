"""
Configuration management for AI Crime Detection Service
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Service settings
    ai_service_port: int = 8000
    debug: bool = True

    # Video input
    video_source: str = "0"  # Webcam by default, or RTSP URL, or file path
    camera_id: str = "CAM-001"

    # Detection settings
    detection_threshold: float = 0.6
    analysis_fps: int = 5  # Frames per second to analyze
    buffer_duration_seconds: int = 5  # 5 seconds pre-event buffer
    post_incident_duration_seconds: int = 5  # 5 seconds post-event recording

    # Model settings
    model_device: str = "cpu"  # 'cuda' or 'cpu'

    # Backend integration
    backend_url: str = "http://localhost:5000"
    backend_timeout_seconds: int = 30

    # Storage
    recordings_dir: Path = Path(__file__).parent.parent / "recordings"
    max_recordings_gb: int = 10
    retention_days: int = 7

    # WebSocket
    ws_heartbeat_interval: int = 30
    max_ws_connections: int = 100

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure recordings directory exists
settings.recordings_dir.mkdir(parents=True, exist_ok=True)
