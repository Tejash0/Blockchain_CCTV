"""
AI Crime Detection Service - Main Application
FastAPI server for real-time video analysis and incident detection
"""
import asyncio
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import numpy as np

from .config import settings
from .core.video_buffer import VideoBuffer
from .core.stream_processor import StreamProcessor
from .core.recording_manager import RecordingManager, IncidentRecording
from .core.hash_uploader import HashUploader, UploadResult
from .models.violence_detector import ViolenceDetector, DetectionResult
from .api.websocket import manager as ws_manager


# Global state
class AppState:
    buffer: VideoBuffer = None
    processor: StreamProcessor = None
    detector: ViolenceDetector = None
    recorder: RecordingManager = None
    uploader: HashUploader = None
    is_detecting: bool = False
    last_detection: DetectionResult = None
    analysis_frames: list = []


state = AppState()


def on_frame_callback(frame: np.ndarray):
    """Called for every frame - adds to buffer and active recording."""
    if state.buffer:
        state.buffer.add_frame(frame)

    # Add frame to active recording (captures entire event duration)
    if state.recorder and state.recorder.is_recording:
        state.recorder.add_frame(frame)


def on_analysis_frame_callback(frame: np.ndarray):
    """Called for analysis frames - runs detection."""
    if not state.is_detecting or state.detector is None:
        return

    # Collect frames for temporal analysis
    state.analysis_frames.append(frame)

    # Analyze every 5 frames (1 second at 5 fps) for faster response
    if len(state.analysis_frames) >= 5:
        frames_array = np.array(state.analysis_frames)
        state.analysis_frames = state.analysis_frames[-2:]  # Keep small overlap

        # Run detection
        result = state.detector.detect(frames_array)
        state.last_detection = result

        if result.is_violent:
            print(f"DETECTION: {result.description} (confidence: {result.confidence:.2f})")

            # Send WebSocket alert
            asyncio.run(ws_manager.send_detection_alert(
                detection_type="violence",
                confidence=result.confidence,
                camera_id=settings.camera_id,
                description=result.description
            ))

            # Start or continue event recording
            if state.recorder:
                if not state.recorder.is_recording:
                    # First detection - start new event
                    state.recorder.start_event(
                        detection_type="violence",
                        confidence=result.confidence
                    )
                else:
                    # Event ongoing - extend recording
                    state.recorder.continue_event(confidence=result.confidence)


def on_recording_complete(recording: IncidentRecording):
    """Called when a recording is saved."""
    print(f"Recording complete: {recording.filepath}")

    # Send WebSocket alert
    asyncio.run(ws_manager.send_recording_alert(
        status="completed",
        camera_id=recording.camera_id,
        video_hash=recording.video_hash,
        filepath=str(recording.filepath)
    ))

    # Upload to backend for blockchain storage
    if state.uploader:
        result = state.uploader.upload_recording_sync(recording)

        if result.success:
            print(f"Uploaded to blockchain: TX {result.transaction_hash}")
            asyncio.run(ws_manager.send_recording_alert(
                status="blockchain_confirmed",
                camera_id=recording.camera_id,
                video_hash=result.video_hash,
                transaction_hash=result.transaction_hash
            ))
        else:
            print(f"Upload failed: {result.error}")
            asyncio.run(ws_manager.send_recording_alert(
                status="upload_failed",
                camera_id=recording.camera_id,
                video_hash=recording.video_hash
            ))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    # Startup
    print("Starting AI Crime Detection Service...")

    # Initialize components
    state.buffer = VideoBuffer(
        duration_seconds=settings.buffer_duration_seconds,
        fps=30
    )

    state.detector = ViolenceDetector(
        threshold=settings.detection_threshold,
        device=settings.model_device,
        use_deep_learning=False  # Use motion-based for demo
    )

    state.recorder = RecordingManager(
        buffer=state.buffer,
        recordings_dir=settings.recordings_dir,
        post_incident_duration=settings.post_incident_duration_seconds,
        on_recording_complete=on_recording_complete
    )

    state.uploader = HashUploader(
        backend_url=settings.backend_url,
        timeout=settings.backend_timeout_seconds
    )

    state.processor = StreamProcessor(
        source=settings.video_source,
        target_fps=30,
        analysis_fps=settings.analysis_fps,
        on_frame=on_frame_callback,
        on_analysis_frame=on_analysis_frame_callback
    )

    print(f"Components initialized. Camera: {settings.camera_id}")

    yield

    # Shutdown
    print("Shutting down AI Crime Detection Service...")
    if state.processor:
        state.processor.stop()


# Create FastAPI app
app = FastAPI(
    title="AI Crime Detection Service",
    description="Real-time video analysis for violence and anomaly detection",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response models
class StartDetectionRequest(BaseModel):
    video_source: Optional[str] = None
    threshold: Optional[float] = None


class StatusResponse(BaseModel):
    status: str
    is_detecting: bool
    camera_id: str
    video_source: str
    buffer_size: int
    buffer_duration: float
    fps: float
    detection_threshold: float
    last_detection: Optional[dict] = None
    websocket_connections: int


# REST API Endpoints
@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "AI Crime Detection"}


@app.get("/api/ai/status", response_model=StatusResponse)
async def get_status():
    """Get current detection status."""
    return StatusResponse(
        status="running" if state.processor and state.processor.is_running else "stopped",
        is_detecting=state.is_detecting,
        camera_id=settings.camera_id,
        video_source=settings.video_source,
        buffer_size=state.buffer.size if state.buffer else 0,
        buffer_duration=state.buffer.duration if state.buffer else 0,
        fps=state.processor.actual_fps if state.processor else 0,
        detection_threshold=settings.detection_threshold,
        last_detection={
            "is_violent": state.last_detection.is_violent,
            "confidence": state.last_detection.confidence,
            "description": state.last_detection.description
        } if state.last_detection else None,
        websocket_connections=ws_manager.connection_count
    )


@app.post("/api/ai/start")
async def start_detection(request: StartDetectionRequest = None):
    """Start video stream and detection."""
    if request and request.video_source:
        settings.video_source = request.video_source
        state.processor.source = request.video_source

    if request and request.threshold:
        settings.detection_threshold = request.threshold
        state.detector.threshold = request.threshold

    if not state.processor.is_running:
        success = state.processor.start()
        if not success:
            raise HTTPException(status_code=500, detail="Failed to start video stream")

    state.is_detecting = True
    state.analysis_frames = []

    return {"status": "started", "camera_id": settings.camera_id}


@app.post("/api/ai/stop")
async def stop_detection():
    """Stop detection (keeps stream running)."""
    state.is_detecting = False
    return {"status": "stopped"}


@app.post("/api/ai/stop-stream")
async def stop_stream():
    """Stop video stream completely."""
    state.is_detecting = False
    if state.processor:
        state.processor.stop()
    return {"status": "stream_stopped"}


@app.post("/api/ai/trigger-test")
async def trigger_test_recording():
    """Manually trigger a test recording (for demo purposes)."""
    if not state.recorder:
        raise HTTPException(status_code=500, detail="Recorder not initialized")

    if state.buffer.size < 10:
        raise HTTPException(status_code=400, detail="Buffer too small - wait for more frames")

    success = state.recorder.trigger_test_recording()

    if success:
        return {"status": "recording_triggered", "message": "Test recording started - will save in ~7 seconds"}
    else:
        return {"status": "already_recording"}


@app.get("/api/ai/recordings")
async def list_recordings():
    """List saved recordings."""
    recordings = []
    for filepath in settings.recordings_dir.glob("*.mp4"):
        recordings.append({
            "filename": filepath.name,
            "size_mb": round(filepath.stat().st_size / (1024 * 1024), 2),
            "created": filepath.stat().st_mtime
        })

    recordings.sort(key=lambda x: x["created"], reverse=True)
    return {"recordings": recordings}


# WebSocket endpoint
@app.websocket("/ws/alerts")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time alerts."""
    await ws_manager.connect(websocket)

    try:
        # Send initial status
        await ws_manager.send_status_update(
            camera_id=settings.camera_id,
            is_detecting=state.is_detecting,
            fps=state.processor.actual_fps if state.processor else 0,
            buffer_size=state.buffer.size if state.buffer else 0
        )

        # Keep connection alive
        while True:
            try:
                # Wait for messages (ping/pong)
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=settings.ws_heartbeat_interval
                )

                # Handle ping
                if data == "ping":
                    await websocket.send_text("pong")

            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_text("heartbeat")

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


# Run with: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.ai_service_port,
        reload=settings.debug
    )
