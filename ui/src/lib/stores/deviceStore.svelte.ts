/** Svelte 5 runes-based device state management. */
import { apiClient, type DeviceState, type Catalog, type CANStatus, type CANNode, type ECUFull } from '$lib/api/client';

export interface ECUFrame {
  channel?: string;
  ts: number;
  arb_id: string;
  pgn: string;
  sa: string;
  data: string;
}

export interface SPNValue {
  spn: number;
  pgn: string;       // hex PGN as sent by backend e.g. "0F004"
  label: string;
  value: number;
  unit: string;
  spec_min: number;
  spec_max: number | null;
}

export interface UnknownFrame {
  pgn: string;       // hex string as sent by backend e.g. "FFC6"
  arb_id: string;    // full arb ID hex e.g. "0CFFC600"
  data: string;      // hex payload e.g. "DC0001FFFFFFFFFF"
  count: number;
  last_ts: number;
}

export interface CANStatusState {
  connected: boolean;
  interface: string;
  channel: string;
  sa: number;
  address_claimed: boolean;
  state: 'disconnected' | 'connecting' | 'claiming' | 'claimed' | 'cannot_claim';
}

const defaultCANStatus: CANStatusState = {
  connected: false,
  interface: '',
  channel: '',
  sa: 0x82,
  address_claimed: false,
  state: 'disconnected',
};

class DeviceStore {
  // Device state (populated via GET_ALL_SETTINGS after selecting an SSS2 node)
  deviceState = $state<DeviceState | null>(null);
  catalog = $state<Catalog | null>(null);
  isLoading = $state<boolean>(false);
  error = $state<string | null>(null);

  // CAN network state
  canStatus = $state<CANStatusState>({ ...defaultCANStatus });
  discoveredNodes = $state<Record<number, CANNode & { sa: number }>>({});
  connectedSSS2SA = $state<number | null>(null);

  // ECU selection
  selectedECUId = $state<string | null>(null);
  selectedECU = $state<ECUFull | null>(null);

  // ECU CAN frame monitor (ring buffer, newest first) — legacy combined buffer
  ecuFrames = $state<ECUFrame[]>([]);

  // Per-channel frame buffers (keyed by channel name e.g. "can0", "can1")
  framesByChannel = $state<Record<string, ECUFrame[]>>({});

  // Per-channel decoded SPNs
  spnsByChannel = $state<Record<string, Record<string, SPNValue>>>({});

  // Active monitor bus channels (added by user via Monitor Buses UI)
  monitorChannels = $state<string[]>([]);

  // ECU SPN monitoring
  monitoredECUSA = $state<number | null>(null);
  spnValues = $state<Record<string, SPNValue>>({});
  unknownFrames = $state<Record<string, UnknownFrame>>({});

  // Potentiometers pinned to Dashboard (plain object for reliable Svelte 5 reactivity)
  pinnedPotIds = $state<Record<string, true>>({});

  // Derived
  ignitionState = $derived(this.deviceState?.ignition ?? false);
}

const store = new DeviceStore();

export const deviceStore = store;

// ---------- State ----------

export async function fetchState(sss2_sa?: number): Promise<void> {
  const sa = sss2_sa ?? store.connectedSSS2SA ?? 0x80;
  store.isLoading = true;
  store.error = null;
  try {
    const state = await apiClient.getState(sa);
    store.deviceState = state;
    if (sa !== null) store.connectedSSS2SA = sa;
  } catch (e) {
    store.error = e instanceof Error ? e.message : 'Failed to fetch state';
    console.error('Failed to fetch state:', e);
  } finally {
    store.isLoading = false;
  }
}

export async function updateState(updates: Partial<DeviceState>): Promise<void> {
  const sa = store.connectedSSS2SA ?? 0x80;
  store.isLoading = true;
  store.error = null;
  try {
    const filteredUpdates = { ...updates };
    if (filteredUpdates.potentiometers) {
      const cleanedPotentiometers: Record<string, any> = {};
      for (const [key, value] of Object.entries(filteredUpdates.potentiometers)) {
        const { application, wire_color, ...rest } = value as any;
        cleanedPotentiometers[key] = rest;
      }
      filteredUpdates.potentiometers = cleanedPotentiometers;
    }
    const state = await apiClient.updateState(filteredUpdates, sa);
    store.deviceState = state;
  } catch (e) {
    store.error = e instanceof Error ? e.message : 'Failed to update state';
    console.error('Failed to update state:', e);
    throw e;
  } finally {
    store.isLoading = false;
  }
}

// ---------- Catalog ----------

export async function fetchCatalog(): Promise<void> {
  store.isLoading = true;
  store.error = null;
  try {
    store.catalog = await apiClient.getCatalog();
  } catch (e) {
    store.error = e instanceof Error ? e.message : 'Failed to fetch catalog';
    console.error('Failed to fetch catalog:', e);
  } finally {
    store.isLoading = false;
  }
}

// ---------- CAN ----------

export async function fetchCANStatus(): Promise<void> {
  try {
    const status = await apiClient.getCANStatus();
    store.canStatus = {
      connected: status.connected,
      interface: status.interface,
      channel: status.channel,
      sa: status.sa,
      address_claimed: status.address_claimed,
      state: status.state,
    };
  } catch (e) {
    console.error('Failed to fetch CAN status:', e);
  }
}

export async function connectCAN(iface: string, channel: string, bitrate: number): Promise<void> {
  store.isLoading = true;
  store.error = null;
  try {
    const status = await apiClient.connectCAN(iface, channel, bitrate);
    store.canStatus = {
      connected: status.connected,
      interface: status.interface,
      channel: status.channel,
      sa: status.sa,
      address_claimed: status.address_claimed,
      state: status.state,
    };
  } catch (e) {
    store.error = e instanceof Error ? e.message : 'Failed to connect CAN';
    console.error('Failed to connect CAN:', e);
    throw e;
  } finally {
    store.isLoading = false;
  }
}

export async function disconnectCAN(): Promise<void> {
  store.isLoading = true;
  store.error = null;
  try {
    const status = await apiClient.disconnectCAN();
    store.canStatus = { ...defaultCANStatus, ...status };
    store.discoveredNodes = {};
    store.connectedSSS2SA = null;
    store.deviceState = null;
  } catch (e) {
    store.error = e instanceof Error ? e.message : 'Failed to disconnect CAN';
    console.error('Failed to disconnect CAN:', e);
    throw e;
  } finally {
    store.isLoading = false;
  }
}

export async function scanCANNodes(): Promise<void> {
  store.isLoading = true;
  store.error = null;
  try {
    const result = await apiClient.scanCANNodes();
    const nodes: Record<number, CANNode & { sa: number }> = {};
    for (const [saStr, node] of Object.entries(result.nodes)) {
      const sa = parseInt(saStr, 10);
      nodes[sa] = { ...node, sa };
    }
    store.discoveredNodes = nodes;
  } catch (e) {
    store.error = e instanceof Error ? e.message : 'Failed to scan CAN nodes';
    console.error('Failed to scan:', e);
    throw e;
  } finally {
    store.isLoading = false;
  }
}

export function addDiscoveredNode(sa: number, node: CANNode): void {
  store.discoveredNodes = { ...store.discoveredNodes, [sa]: { ...node, sa } };
}

export async function selectSSS2(sa: number): Promise<void> {
  store.connectedSSS2SA = sa;
  await fetchState(sa);
}

// ---------- ECU ----------

export async function setSelectedECU(ecuId: string | null): Promise<void> {
  if (ecuId === null) {
    store.selectedECUId = null;
    store.selectedECU = null;
    if (typeof window !== 'undefined') localStorage.removeItem('selectedECUId');
    return;
  }
  store.isLoading = true;
  store.error = null;
  try {
    const ecu = await apiClient.getECU(ecuId);
    store.selectedECUId = ecuId;
    store.selectedECU = ecu;
    if (typeof window !== 'undefined') localStorage.setItem('selectedECUId', ecuId);
  } catch (e) {
    store.error = e instanceof Error ? e.message : 'Failed to load ECU';
    console.error('Failed to load ECU:', e);
  } finally {
    store.isLoading = false;
  }
}

export function loadSelectedECUFromStorage(): void {
  if (typeof window !== 'undefined') {
    const storedECUId = localStorage.getItem('selectedECUId');
    if (storedECUId) setSelectedECU(storedECUId);
  }
}

export async function reloadSelectedECU(): Promise<void> {
  if (store.selectedECUId) await setSelectedECU(store.selectedECUId);
}

// ---------- ECU CAN Frame Monitor ----------

export function addECUFrame(frame: ECUFrame): void {
  store.ecuFrames = [frame, ...store.ecuFrames].slice(0, 200);
}

export function addFrameForChannel(channel: string, frame: ECUFrame): void {
  const existing = store.framesByChannel[channel] ?? [];
  store.framesByChannel = {
    ...store.framesByChannel,
    [channel]: [frame, ...existing].slice(0, 200),
  };
  // Also maintain the legacy combined buffer
  store.ecuFrames = [frame, ...store.ecuFrames].slice(0, 200);
}

export function updateSPNsForChannel(channel: string, updates: Record<string, SPNValue>): void {
  const existing = store.spnsByChannel[channel] ?? {};
  store.spnsByChannel = {
    ...store.spnsByChannel,
    [channel]: { ...existing, ...updates },
  };
}

// ---------- Monitor buses ----------

export async function connectMonitorBus(channel: string, bitrate: number): Promise<void> {
  try {
    await apiClient.connectMonitorBus(channel, bitrate);
    if (!store.monitorChannels.includes(channel)) {
      store.monitorChannels = [...store.monitorChannels, channel];
    }
  } catch (e) {
    store.error = e instanceof Error ? e.message : 'Failed to connect monitor bus';
    throw e;
  }
}

export async function disconnectMonitorBus(channel: string): Promise<void> {
  try {
    await apiClient.disconnectMonitorBus(channel);
  } catch (e) {
    console.error('Failed to disconnect monitor bus:', e);
  }
  store.monitorChannels = store.monitorChannels.filter(ch => ch !== channel);
  const { [channel]: _, ...rest } = store.framesByChannel;
  store.framesByChannel = rest;
  const { [channel]: __, ...restSpn } = store.spnsByChannel;
  store.spnsByChannel = restSpn;
}

// ---------- ECU SPN Monitor ----------

export function togglePinnedPot(id: string): void {
  if (store.pinnedPotIds[id]) {
    const { [id]: _, ...rest } = store.pinnedPotIds;
    store.pinnedPotIds = rest as Record<string, true>;
  } else {
    store.pinnedPotIds = { ...store.pinnedPotIds, [id]: true };
  }
}

export function setMonitoredECU(sa: number | null): void {
  store.monitoredECUSA = sa;
  store.spnValues = {};
  store.unknownFrames = {};
}

export function updateSPNValues(updates: Record<string, SPNValue>): void {
  store.spnValues = { ...store.spnValues, ...updates };
}

export function addUnknownFrame(frame: ECUFrame): void {
  const prev = store.unknownFrames[frame.pgn];
  store.unknownFrames = {
    ...store.unknownFrames,
    [frame.pgn]: {
      pgn: frame.pgn,
      arb_id: frame.arb_id,
      data: frame.data,
      count: (prev?.count ?? 0) + 1,
      last_ts: frame.ts,
    },
  };
}
