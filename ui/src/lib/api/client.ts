/** API client wrapper for backend communication. */

const API_BASE = import.meta.env.VITE_API_BASE || '/api';

export interface HealthResponse {
  status: string;
  version: string;
  connected: boolean;
}

export interface Catalog {
  potentiometers: PotentiometerDefinition[];
  vouts: any[];
  pwms: any[];
  can_channels: any[];
  j1708: any[];
}

export interface PotentiometerDefinition {
  id: string;
  name: string;
  port: number;
  pin: string;
  resistance: string;
  ecm_fault_low: number;
  ecm_fault_high: number;
  type: string;
}

export interface DeviceState {
  sss2_sa: number | null;
  last_updated: string | null;
  ignition: boolean;
  potentiometers: Record<string, PotentiometerState>;
  potentiometer_power_groups?: Record<string, PotentiometerPowerGroup>;
  vouts: Record<string, any>;
  pwms: Record<string, any>;
  can: Record<string, any>;
  j1708: Record<string, any>;
}

export interface PotentiometerState {
  wiper_position: number;
  voltage: number;
  enabled: boolean;
  application?: string;
  wire_color?: string;
}

export interface PotentiometerPowerGroup {
  group_id: string;
  voltage_setting: '5V' | '12V';
  potentiometers: string[];
}

export interface IgnitionRequest {
  on: boolean;
  sss2_sa?: number;
}

export interface IgnitionResponse {
  accepted: boolean;
  executed: boolean;
  detail: string;
  ignition: boolean;
}

export interface CANInterface {
  interface: string;
  channel: string;
  bitrate: number;
  description: string;
}

export interface CANStatus {
  connected: boolean;
  interface: string;
  channel: string;
  bitrate: number;
  sa: number;
  address_claimed: boolean;
  state: 'disconnected' | 'connecting' | 'claiming' | 'claimed' | 'cannot_claim';
}

export interface CANNode {
  name_int: number;
  name_hex: string;
  is_sss2: boolean;
  label?: string;
  function?: string;
  manufacturer?: string;
  industry_group?: string;
  vehicle_system?: string;
}

export interface PinConfiguration {
  wire_color: string;
  ecu_function: string;
}

export interface ECUItem {
  id: string;
  name: string;
  model: string;
  serial_number: string;
  created_at: string;
  updated_at: string;
}

export interface ECUFull {
  id: string;
  name: string;
  model: string;
  serial_number: string;
  pictures: string[];
  pins: Record<string, PinConfiguration>;
  created_at: string;
  updated_at: string;
}

export interface ECUCreate {
  name: string;
  model?: string;
  serial_number?: string;
  pictures?: string[];
  pins?: Record<string, PinConfiguration>;
}

export interface ECUUpdate {
  name?: string;
  model?: string;
  serial_number?: string;
  pictures?: string[];
  pins?: Record<string, PinConfiguration>;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>('/health');
  }

  async getCatalog(): Promise<Catalog> {
    return this.request<Catalog>('/catalog');
  }

  // ---------- SSS2 state / ignition ----------

  async getState(sss2_sa: number = 0x80): Promise<DeviceState> {
    return this.request<DeviceState>(`/sss2/state?sss2_sa=${sss2_sa}`);
  }

  async updateState(state: Partial<DeviceState>, sss2_sa: number = 0x80): Promise<DeviceState> {
    return this.request<DeviceState>('/sss2/state', {
      method: 'PUT',
      body: JSON.stringify({ state, sss2_sa }),
    });
  }

  async setIgnition(on: boolean, sss2_sa: number = 0x80): Promise<IgnitionResponse> {
    return this.request<IgnitionResponse>('/sss2/ignition', {
      method: 'POST',
      body: JSON.stringify({ on, sss2_sa }),
    });
  }

  // ---------- CAN ----------

  async listCANInterfaces(): Promise<CANInterface[]> {
    return this.request<CANInterface[]>('/can/interfaces');
  }

  async getCANStatus(): Promise<CANStatus> {
    return this.request<CANStatus>('/can/status');
  }

  async connectCAN(iface: string, channel: string, bitrate: number): Promise<CANStatus> {
    return this.request<CANStatus>('/can/connect', {
      method: 'POST',
      body: JSON.stringify({ interface: iface, channel, bitrate }),
    });
  }

  async disconnectCAN(): Promise<CANStatus> {
    return this.request<CANStatus>('/can/disconnect', { method: 'POST' });
  }

  async scanCANNodes(timeout_ms: number = 1250): Promise<{ nodes: Record<string, CANNode> }> {
    return this.request<{ nodes: Record<string, CANNode> }>('/can/scan', {
      method: 'POST',
      body: JSON.stringify({ timeout_ms }),
    });
  }

  async getCANNodes(): Promise<{ nodes: Record<string, CANNode> }> {
    return this.request<{ nodes: Record<string, CANNode> }>('/can/nodes');
  }

  async connectMonitorBus(channel: string, bitrate: number): Promise<{ channel: string; status: string }> {
    return this.request('/can/monitor/connect', {
      method: 'POST',
      body: JSON.stringify({ channel, bitrate }),
    });
  }

  async disconnectMonitorBus(channel: string): Promise<{ channel: string; status: string }> {
    return this.request(`/can/monitor/${channel}`, { method: 'DELETE' });
  }

  async getMonitorStatus(): Promise<{ channel: string; status: string }[]> {
    return this.request('/can/monitor/status');
  }

  // ---------- ECU ----------

  async listECUs(): Promise<ECUItem[]> {
    return this.request<ECUItem[]>('/ecu');
  }

  async getECU(ecuId: string): Promise<ECUFull> {
    return this.request<ECUFull>(`/ecu/${ecuId}`);
  }

  async createECU(ecu: ECUCreate): Promise<ECUFull> {
    return this.request<ECUFull>('/ecu', {
      method: 'POST',
      body: JSON.stringify(ecu),
    });
  }

  async updateECU(ecuId: string, updates: ECUUpdate): Promise<ECUFull> {
    return this.request<ECUFull>(`/ecu/${ecuId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  }

  async deleteECU(ecuId: string): Promise<void> {
    await this.request(`/ecu/${ecuId}`, {
      method: 'DELETE',
    });
  }
}

export const apiClient = new ApiClient();
