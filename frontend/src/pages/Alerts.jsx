import { useState, useEffect } from 'react';
import useWebSocket from '../hooks/useWebSocket';

function Alerts() {
  const { isConnected, alerts, status, clearAlerts } = useWebSocket();
  const [aiStatus, setAiStatus] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  // Fetch AI service status
  const fetchStatus = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/ai/status');
      if (response.ok) {
        const data = await response.json();
        setAiStatus(data);
      }
    } catch (error) {
      console.error('Failed to fetch AI status:', error);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  // Start detection
  const startDetection = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/ai/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      if (response.ok) {
        fetchStatus();
      }
    } catch (error) {
      console.error('Failed to start detection:', error);
    }
    setIsLoading(false);
  };

  // Stop detection
  const stopDetection = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/ai/stop', {
        method: 'POST'
      });
      if (response.ok) {
        fetchStatus();
      }
    } catch (error) {
      console.error('Failed to stop detection:', error);
    }
    setIsLoading(false);
  };

  // Trigger test recording
  const triggerTestRecording = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/ai/trigger-test', {
        method: 'POST'
      });
      const data = await response.json();
      alert(data.status || data.detail);
    } catch (error) {
      console.error('Failed to trigger test:', error);
      alert('Failed to trigger test recording');
    }
  };

  const formatTimestamp = (isoString) => {
    return new Date(isoString).toLocaleString();
  };

  const getAlertColor = (type) => {
    switch (type) {
      case 'violence':
        return 'bg-red-100 border-red-500 text-red-800';
      case 'anomaly':
        return 'bg-orange-100 border-orange-500 text-orange-800';
      case 'recording':
        return 'bg-blue-100 border-blue-500 text-blue-800';
      default:
        return 'bg-gray-100 border-gray-500 text-gray-800';
    }
  };

  const getAlertIcon = (type) => {
    switch (type) {
      case 'violence':
        return '🚨';
      case 'anomaly':
        return '⚠️';
      case 'recording':
        return '📹';
      default:
        return 'ℹ️';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">AI Crime Detection</h1>
        <div className="flex items-center gap-4">
          <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-sm ${
            isConnected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
          }`}>
            <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
            {isConnected ? 'Connected' : 'Disconnected'}
          </div>
        </div>
      </div>

      {/* Status Panel */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">Detection Status</h2>

        {aiStatus ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="bg-gray-50 p-3 rounded">
              <div className="text-sm text-gray-500">Status</div>
              <div className={`font-semibold ${aiStatus.is_detecting ? 'text-green-600' : 'text-gray-600'}`}>
                {aiStatus.is_detecting ? 'Detecting' : 'Stopped'}
              </div>
            </div>
            <div className="bg-gray-50 p-3 rounded">
              <div className="text-sm text-gray-500">Camera</div>
              <div className="font-semibold">{aiStatus.camera_id}</div>
            </div>
            <div className="bg-gray-50 p-3 rounded">
              <div className="text-sm text-gray-500">Buffer</div>
              <div className="font-semibold">{aiStatus.buffer_duration.toFixed(1)}s</div>
            </div>
            <div className="bg-gray-50 p-3 rounded">
              <div className="text-sm text-gray-500">FPS</div>
              <div className="font-semibold">{aiStatus.fps.toFixed(1)}</div>
            </div>
          </div>
        ) : (
          <div className="text-gray-500 mb-4">Loading status...</div>
        )}

        <div className="flex gap-3">
          <button
            onClick={startDetection}
            disabled={isLoading || aiStatus?.is_detecting}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Start Detection
          </button>
          <button
            onClick={stopDetection}
            disabled={isLoading || !aiStatus?.is_detecting}
            className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Stop Detection
          </button>
          <button
            onClick={triggerTestRecording}
            disabled={isLoading}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            Test Recording
          </button>
        </div>
      </div>

      {/* Alerts Panel */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold">Real-time Alerts</h2>
          <button
            onClick={clearAlerts}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            Clear All
          </button>
        </div>

        {alerts.length === 0 ? (
          <div className="text-center text-gray-500 py-8">
            No alerts yet. Start detection to monitor for incidents.
          </div>
        ) : (
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {alerts.map((alert, index) => (
              <div
                key={`${alert.timestamp}-${index}`}
                className={`border-l-4 p-4 rounded ${getAlertColor(alert.type)}`}
              >
                <div className="flex justify-between items-start">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">{getAlertIcon(alert.type)}</span>
                    <div>
                      <div className="font-semibold capitalize">{alert.type} Alert</div>
                      <div className="text-sm">{alert.message}</div>
                    </div>
                  </div>
                  <div className="text-right text-sm">
                    <div>Confidence: {(alert.confidence * 100).toFixed(0)}%</div>
                    <div className="text-xs opacity-75">{formatTimestamp(alert.timestamp)}</div>
                  </div>
                </div>

                {alert.data?.videoHash && (
                  <div className="mt-2 text-xs font-mono bg-white bg-opacity-50 p-2 rounded">
                    Hash: {alert.data.videoHash.slice(0, 20)}...
                    {alert.data.transactionHash && (
                      <span className="ml-2">TX: {alert.data.transactionHash.slice(0, 20)}...</span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Instructions */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
        <strong>How it works:</strong>
        <ul className="mt-2 list-disc list-inside space-y-1">
          <li>Start the AI service: <code className="bg-blue-100 px-1 rounded">cd ai-service && python -m app.main</code></li>
          <li>Click "Start Detection" to begin monitoring your webcam</li>
          <li>When violence/anomaly is detected, video is automatically saved and hashed to blockchain</li>
          <li>Alerts appear here in real-time via WebSocket</li>
        </ul>
      </div>
    </div>
  );
}

export default Alerts;
