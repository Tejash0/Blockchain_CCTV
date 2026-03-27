"""
AI Crime Detection Service - Main Application
FastAPI server for real-time video analysis and incident detection
"""
import asyncio
import threading
from contextlib import asynccontextmanager
import os
import tempfile
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional
import numpy as np

from .config import settings
from .core.video_buffer import VideoBuffer
from .core.stream_processor import StreamProcessor
from .core.recording_manager import RecordingManager, IncidentRecording
from .core.hash_uploader import HashUploader, UploadResult
from .core.forensic_report import ForensicReportGenerator
from .models.violence_detector import ViolenceDetector, DetectionResult
from .api.websocket import manager as ws_manager


# Global state
class AppState:
    def __init__(self):
        self.buffer = None
        self.processor = None
        self.detector = None
        self.recorder = None
        self.uploader = None
        self.report_generator = None
        self.is_detecting = False
        self.last_detection = None
        self.analysis_frames = []


state = AppState()


def on_frame_callback(frame: np.ndarray):
    """Called for every frame - adds to buffer and active recording."""
    if state.buffer is None:
        # Re-initialize buffer if lost (e.g. after module reload)
        from .core.video_buffer import VideoBuffer
        state.buffer = VideoBuffer(duration_seconds=settings.buffer_duration_seconds, fps=30)
        print(f"[DEBUG] Buffer re-initialized: {state.buffer.max_frames} max frames")
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

    # Generate forensic report if available
    if state.report_generator:
        try:
            import os
            reports_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                'cloud-storage', 'reports'
            )
            report = state.report_generator.generate_report(
                video_path=str(recording.filepath),
                video_hash=recording.video_hash,
                camera_id=recording.camera_id,
                timestamp=recording.timestamp,
                event_type=recording.event_type or recording.detection_type,
                confidence=recording.confidence
            )
            state.report_generator.save_report(report, reports_dir)
            recording.report_hash = report.report_hash
            recording.ai_model_version = report.ai_model_version
            print(f"Forensic report generated: hash={report.report_hash}")
        except Exception as e:
            print(f"Forensic report generation failed: {e}")

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

            # Send email alert if configured
            recipients = [r.strip() for r in settings.alert_email_recipients.split(",") if r.strip()]
            if recipients:
                from .utils.email_alert import send_incident_email
                send_incident_email(
                    smtp_host=settings.alert_smtp_host,
                    smtp_port=settings.alert_smtp_port,
                    sender=settings.alert_email_sender,
                    password=settings.alert_email_password,
                    recipients=recipients,
                    camera_id=recording.camera_id,
                    event_type=recording.event_type or recording.detection_type,
                    confidence=recording.confidence,
                    video_hash=result.video_hash,
                    transaction_hash=result.transaction_hash,
                    timestamp=recording.timestamp,
                )
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
    print(f"Buffer initialized: {state.buffer}, max_frames={state.buffer.max_frames}")

    state.detector = ViolenceDetector(
        threshold=settings.detection_threshold,
        device=settings.model_device,
        use_deep_learning=True,
        model_path=settings.yolo_model
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

    state.report_generator = ForensicReportGenerator(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model
    )
    if state.report_generator.is_available:
        print(f"Forensic report generator ready (model: {state.report_generator.model_name})")
    else:
        print("Forensic report generator: Gemini unavailable, using fallback reports")

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
        fps=float(state.processor.actual_fps) if state.processor else 0,
        detection_threshold=settings.detection_threshold,
        last_detection={
            "is_violent": bool(state.last_detection.is_violent),
            "confidence": float(state.last_detection.confidence),
            "description": str(state.last_detection.description)
        } if state.last_detection else None,
        websocket_connections=ws_manager.connection_count
    )


@app.post("/api/ai/start")
async def start_detection(request: StartDetectionRequest = None):
    """Start video stream and detection."""
    source_changed = False
    if request and request.video_source:
        settings.video_source = request.video_source
        state.processor.source = request.video_source
        source_changed = True

    if request and request.threshold:
        settings.detection_threshold = request.threshold
        state.detector.threshold = request.threshold

    if source_changed and state.processor.is_running:
        state.processor.stop()

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


@app.post("/api/ai/k2a")
async def compute_k2a(video: UploadFile = File(...)):
    """
    Compute K2A perceptual hash for an uploaded video.
    Single authoritative Python implementation — called by backend so both
    /api/record and /api/verify use identical hashing logic.
    """
    suffix = os.path.splitext(video.filename or "video.mp4")[1] or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await video.read())
        tmp_path = tmp.name
    try:
        from .utils.k2a_hash import compute_video_k2a_hash
        k2a_hash = compute_video_k2a_hash(tmp_path)
        return JSONResponse(content={"k2a_hash": k2a_hash})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"K2A computation failed: {str(e)}")
    finally:
        os.unlink(tmp_path)


@app.post("/api/ai/analyze")
async def analyze_video(
    video: UploadFile = File(...),
    camera_id: str = Form("VERIFY"),
    event_type: str = Form("verification"),
    confidence: float = Form(1.0)
):
    """
    Analyze an uploaded video file with Gemini and return a forensic report.
    Used by the backend verify endpoint — does NOT store anything.
    """
    if not state.report_generator:
        raise HTTPException(status_code=503, detail="Report generator not initialized")

    # Write upload to a temp file (cv2 needs a path, not a buffer)
    suffix = os.path.splitext(video.filename or "video.mp4")[1] or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await video.read())
        tmp_path = tmp.name

    try:
        import hashlib, time
        content = open(tmp_path, "rb").read()
        video_hash = "0x" + hashlib.sha256(content).hexdigest()

        report = state.report_generator.generate_report(
            video_path=tmp_path,
            video_hash=video_hash,
            camera_id=camera_id,
            timestamp=time.time(),
            event_type=event_type,
            confidence=confidence
        )

        # Save report to cloud-storage/reports/
        reports_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'cloud-storage', 'reports'
        )
        state.report_generator.save_report(report, reports_dir)

        return JSONResponse(content=report.to_dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
    finally:
        os.unlink(tmp_path)


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
