<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import {
    deviceStore,
    fetchState,
    fetchCatalog,
    fetchCANStatus,
    addDiscoveredNode,
    addFrameForChannel,
    updateSPNValues,
    updateSPNsForChannel,
    addUnknownFrame,
    loadSelectedECUFromStorage,
  } from '$lib/stores/deviceStore.svelte';
  import { connectWebSocket, disconnectWebSocket, type WSMessage } from '$lib/api/wsClient';
  import { decodeSPNsFromFrame, type SpnDb } from '$lib/utils/spnDecode';
  import Dashboard from '$lib/pages/Dashboard.svelte';
  import Settings from '$lib/pages/Settings.svelte';
  import IgnitionToggle from '$lib/components/IgnitionToggle.svelte';
  import CANConnectionPanel from '$lib/components/CANConnectionPanel.svelte';
  import NetworkScanPanel from '$lib/components/NetworkScanPanel.svelte';
  import CANMonitorPanel from '$lib/components/CANMonitorPanel.svelte';
  import ConnectionNotification from '$lib/components/ConnectionNotification.svelte';
  import ECUSelector from '$lib/components/ECUSelector.svelte';

  type Route = 'dashboard' | 'settings' | 'network';

  let currentRoute = $state<Route>('dashboard');
  let unsubscribe: (() => void) | null = null;
  let showNetworkPanel = $state(false);
  let spnDb = $state<SpnDb>({});

  const canStatus = $derived(deviceStore.canStatus);

  onMount(() => {
    fetchCatalog();
    fetchCANStatus();
    loadSelectedECUFromStorage();

    // Load SPN database for ECU monitoring
    fetch('/api/can/spn-db').then(r => { if (r.ok) r.json().then(db => { spnDb = db; }); });

    // If already claimed, fetch state from SSS2 (defaults to SA=0x80)
    if (deviceStore.canStatus.address_claimed) {
      fetchState();
    }

    // WebSocket for real-time CAN events
    const wsClient = connectWebSocket();
    unsubscribe = wsClient.subscribe((message: WSMessage) => {
      if (message.type === 'can_status') {
        const prev = deviceStore.canStatus.address_claimed;
        deviceStore.canStatus = {
          connected: message.connected,
          interface: message.interface,
          channel: message.channel,
          sa: message.sa,
          address_claimed: message.address_claimed,
          state: message.state,
        };
        // Auto-fetch state when address is freshly claimed (defaults to SA=0x80)
        if (!prev && message.address_claimed) {
          fetchState();
        }
      } else if (message.type === 'node_discovered') {
        addDiscoveredNode(message.sa, {
          name_int: message.name_int,
          name_hex: message.name_hex,
          is_sss2: message.is_sss2,
        });
      } else if (message.type === 'ecu_frame') {
        const ch = message.frame.channel ?? 'can0';
        addFrameForChannel(ch, message.frame);

        const spnUpdates = decodeSPNsFromFrame(message.frame.pgn, message.frame.data, spnDb);

        // Per-channel SPN storage for monitor panel tabs
        if (Object.keys(spnUpdates).length > 0) updateSPNsForChannel(ch, spnUpdates);

        // Legacy SA-filtered SPN monitoring (SPNMonitorPanel)
        const monSA = deviceStore.monitoredECUSA;
        if (monSA !== null && parseInt(message.frame.sa, 16) === monSA) {
          if (Object.keys(spnUpdates).length > 0) updateSPNValues(spnUpdates);
          else addUnknownFrame(message.frame);
        }
      }
      // state_fetched is handled by explicit fetchState() calls
    });
  });

  onDestroy(() => {
    if (unsubscribe) unsubscribe();
    disconnectWebSocket();
  });

  function navigate(route: Route) {
    currentRoute = route;
  }
</script>

<div class="min-h-screen bg-dark-bg text-white">
  <!-- Fixed Top Navigation -->
  <nav class="fixed top-0 left-0 right-0 z-[100] bg-[#103f03] border-b border-dark-card">
    <div class="flex items-center justify-between px-4 py-3 gap-4 flex-wrap">
      <h1 class="text-xl font-bold whitespace-nowrap">Smart Sensor Simulation 2 (SSS2)</h1>
      <div class="flex items-center gap-3 flex-wrap flex-1">
        <!-- CAN connection controls -->
        <CANConnectionPanel />

        <!-- Navigation -->
        <button
          class="px-4 py-2 rounded bg-dark-card hover:bg-dark-accent transition-colors min-h-touch text-sm"
          onclick={() => navigate('dashboard')}
        >
          Dashboard
        </button>
        <button
          class="px-4 py-2 rounded bg-dark-card hover:bg-dark-accent transition-colors min-h-touch text-sm"
          onclick={() => navigate('settings')}
        >
          Settings
        </button>
        <button
          class="px-4 py-2 rounded bg-dark-card hover:bg-dark-accent transition-colors min-h-touch text-sm"
          onclick={() => navigate('network')}
        >
          Network
        </button>
        <ECUSelector />
        <div class="flex items-center gap-2">
          <span class="text-sm text-gray-400">Ignition</span>
          <IgnitionToggle />
        </div>
      </div>
    </div>
  </nav>

  <!-- Main Content -->
  <main class="relative z-0 pt-24 pb-16 px-4">
    {#if currentRoute === 'dashboard'}
      <Dashboard />
    {:else if currentRoute === 'settings'}
      <Settings />
    {:else if currentRoute === 'network'}
      <div class="max-w-5xl mx-auto py-4">
        <h2 class="text-lg font-semibold mb-4">J1939 Network</h2>
        <NetworkScanPanel />
        <CANMonitorPanel />
      </div>
    {/if}
  </main>

  <!-- Fixed Bottom Footer -->
  <footer class="fixed bottom-0 left-0 right-0 z-[100] bg-[#0a2338] border-t border-dark-card px-4 py-2">
    <div class="flex justify-end">
      <div class="text-sm text-gray-400">
        CAN: {#if canStatus.address_claimed}
          <span class="text-green-400">
            Claimed SA 0x{canStatus.sa.toString(16).toUpperCase().padStart(2, '0')}
            {#if deviceStore.connectedSSS2SA !== null}
              · SSS2 @ 0x{deviceStore.connectedSSS2SA.toString(16).toUpperCase().padStart(2, '0')}
            {/if}
          </span>
        {:else if canStatus.state === 'cannot_claim'}
          <span class="text-red-400">Cannot Claim</span>
        {:else if canStatus.state === 'claiming'}
          <span class="text-yellow-400">Claiming…</span>
        {:else}
          <span class="text-gray-500">Disconnected</span>
        {/if}
      </div>
    </div>
  </footer>

  <!-- Connection Notification (toast) -->
  <ConnectionNotification />
</div>
