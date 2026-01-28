"""
WebSocket handler for real-time alerts
"""
import asyncio
import json
from datetime import datetime
from typing import Set, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect
from dataclasses import dataclass, asdict


@dataclass
class Alert:
    """Alert message structure"""
    type: str  # 'violence', 'anomaly', 'recording', 'status'
    confidence: float
    timestamp: str
    camera_id: str
    message: str
    data: Dict[str, Any] = None

    def to_json(self) -> str:
        d = asdict(self)
        if d['data'] is None:
            d['data'] = {}
        return json.dumps(d)


class ConnectionManager:
    """
    Manages WebSocket connections for real-time alerts.
    """

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        print(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        async with self._lock:
            self.active_connections.discard(websocket)
        print(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        """Send a message to all connected clients."""
        if not self.active_connections:
            return

        disconnected = set()

        async with self._lock:
            for connection in self.active_connections:
                try:
                    await connection.send_text(message)
                except Exception:
                    disconnected.add(connection)

            # Clean up disconnected clients
            self.active_connections -= disconnected

    async def broadcast_alert(self, alert: Alert):
        """Broadcast an alert to all connected clients."""
        await self.broadcast(alert.to_json())

    async def send_detection_alert(
        self,
        detection_type: str,
        confidence: float,
        camera_id: str,
        description: str = ""
    ):
        """
        Send a detection alert.

        Args:
            detection_type: 'violence' or 'anomaly'
            confidence: Detection confidence (0-1)
            camera_id: Camera identifier
            description: Human-readable description
        """
        alert = Alert(
            type=detection_type,
            confidence=confidence,
            timestamp=datetime.now().isoformat(),
            camera_id=camera_id,
            message=description or f"{detection_type.title()} detected",
            data={"source": "ai-detection"}
        )
        await self.broadcast_alert(alert)

    async def send_recording_alert(
        self,
        status: str,  # 'started', 'completed', 'failed'
        camera_id: str,
        video_hash: str = None,
        transaction_hash: str = None,
        filepath: str = None
    ):
        """
        Send a recording status alert.

        Args:
            status: Recording status
            camera_id: Camera identifier
            video_hash: SHA-256 hash of video
            transaction_hash: Blockchain transaction hash
            filepath: Path to saved video
        """
        alert = Alert(
            type="recording",
            confidence=1.0,
            timestamp=datetime.now().isoformat(),
            camera_id=camera_id,
            message=f"Recording {status}",
            data={
                "status": status,
                "videoHash": video_hash,
                "transactionHash": transaction_hash,
                "filepath": filepath
            }
        )
        await self.broadcast_alert(alert)

    async def send_status_update(
        self,
        camera_id: str,
        is_detecting: bool,
        fps: float,
        buffer_size: int
    ):
        """
        Send a status update.

        Args:
            camera_id: Camera identifier
            is_detecting: Whether detection is active
            fps: Current processing FPS
            buffer_size: Current buffer size in frames
        """
        alert = Alert(
            type="status",
            confidence=1.0,
            timestamp=datetime.now().isoformat(),
            camera_id=camera_id,
            message="Status update",
            data={
                "detecting": is_detecting,
                "fps": round(fps, 1),
                "bufferSize": buffer_size
            }
        )
        await self.broadcast_alert(alert)

    @property
    def connection_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)


# Global connection manager instance
manager = ConnectionManager()
