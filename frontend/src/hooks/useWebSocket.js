import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Custom hook for WebSocket connection to AI service
 */
export function useWebSocket(url = 'ws://localhost:8000/ws/alerts') {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [status, setStatus] = useState(null);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 10;

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      wsRef.current = new WebSocket(url);

      wsRef.current.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
        reconnectAttempts.current = 0;
      };

      wsRef.current.onclose = () => {
        console.log('WebSocket disconnected');
        setIsConnected(false);

        // Auto-reconnect with exponential backoff
        if (reconnectAttempts.current < maxReconnectAttempts) {
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttempts.current++;
            connect();
          }, delay);
        }
      };

      wsRef.current.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      wsRef.current.onmessage = (event) => {
        const data = event.data;

        // Handle heartbeat/pong
        if (data === 'heartbeat' || data === 'pong') {
          return;
        }

        try {
          const message = JSON.parse(data);
          setLastMessage(message);

          // Route message by type
          switch (message.type) {
            case 'violence':
            case 'anomaly':
            case 'recording':
              setAlerts(prev => [message, ...prev].slice(0, 100)); // Keep last 100
              break;
            case 'status':
              setStatus(message.data);
              break;
            default:
              console.log('Unknown message type:', message.type);
          }
        } catch (e) {
          console.log('Non-JSON message:', data);
        }
      };
    } catch (error) {
      console.error('WebSocket connection error:', error);
    }
  }, [url]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
  }, []);

  const sendMessage = useCallback((message) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof message === 'string' ? message : JSON.stringify(message));
    }
  }, []);

  const clearAlerts = useCallback(() => {
    setAlerts([]);
  }, []);

  // Connect on mount
  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  // Ping to keep connection alive
  useEffect(() => {
    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send('ping');
      }
    }, 30000);

    return () => clearInterval(pingInterval);
  }, []);

  return {
    isConnected,
    lastMessage,
    alerts,
    status,
    sendMessage,
    clearAlerts,
    connect,
    disconnect
  };
}

export default useWebSocket;
