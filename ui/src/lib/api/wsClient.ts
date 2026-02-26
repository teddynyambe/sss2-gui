/** WebSocket client for CAN status and J1939 network events. */

const API_BASE = import.meta.env.VITE_API_BASE || '/api';

// ---------- Message types ----------

export interface CANStatusMessage {
  type: 'can_status';
  connected: boolean;
  interface: string;
  channel: string;
  bitrate: number;
  sa: number;
  address_claimed: boolean;
  state: 'disconnected' | 'connecting' | 'claiming' | 'claimed' | 'cannot_claim';
}

export interface NodeDiscoveredMessage {
  type: 'node_discovered';
  sa: number;
  name_int: number;
  name_hex: string;
  is_sss2: boolean;
}

export interface StateFetchedMessage {
  type: 'state_fetched';
  sss2_sa: number;
  settings: Record<string, number>;
}

export interface ECUFrameMessage {
  type: 'ecu_frame';
  frame: {
    ts: number;
    arb_id: string;
    pgn: string;
    sa: string;
    data: string;
  };
}

export type WSMessage = CANStatusMessage | NodeDiscoveredMessage | StateFetchedMessage | ECUFrameMessage;
export type WSCallback = (message: WSMessage) => void;

class WebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectInterval: number = 3000;
  private reconnectTimer: number | null = null;
  private callbacks: Set<WSCallback> = new Set();
  private url: string;

  constructor(url: string = '/api/connection/ws') {
    if (url.startsWith('ws://') || url.startsWith('wss://')) {
      this.url = url;
    } else if (API_BASE.startsWith('http://') || API_BASE.startsWith('https://')) {
      const wsProtocol = API_BASE.startsWith('https://') ? 'wss:' : 'ws:';
      const baseUrl = API_BASE.replace(/^https?:/, wsProtocol).replace(/\/$/, '');
      this.url = `${baseUrl}${url.startsWith('/') ? url : '/' + url}`;
    } else {
      // In both dev and prod, use the same host the page was loaded from.
      // Vite proxy (ws: true) forwards /api/... WebSocket upgrades to the backend.
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      this.url = `${protocol}//${window.location.host}${url}`;
    }
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    try {
      this.ws = new WebSocket(this.url);
      this.setupEventHandlers();
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      this.scheduleReconnect();
    }
  }

  private setupEventHandlers(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const message: WSMessage = JSON.parse(event.data);
        this.notifyCallbacks(message);
      } catch (error) {
        console.error('Failed to parse WS message:', error, event.data);
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    this.ws.onclose = () => {
      this.ws = null;
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, this.reconnectInterval);
  }

  private notifyCallbacks(message: WSMessage): void {
    this.callbacks.forEach(cb => {
      try {
        cb(message);
      } catch (error) {
        console.error('WS callback error:', error);
      }
    });
  }

  subscribe(callback: WSCallback): () => void {
    this.callbacks.add(callback);
    return () => this.callbacks.delete(callback);
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.callbacks.clear();
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// Singleton
let wsClientInstance: WebSocketClient | null = null;

export function connectWebSocket(): WebSocketClient {
  if (!wsClientInstance) {
    wsClientInstance = new WebSocketClient();
    wsClientInstance.connect();
  }
  return wsClientInstance;
}

export function disconnectWebSocket(): void {
  if (wsClientInstance) {
    wsClientInstance.disconnect();
    wsClientInstance = null;
  }
}

export function getWebSocketClient(): WebSocketClient | null {
  return wsClientInstance;
}
