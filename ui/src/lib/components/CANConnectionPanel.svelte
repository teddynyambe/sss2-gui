<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { deviceStore, connectCAN, disconnectCAN, fetchCANStatus, connectMonitorBus, disconnectMonitorBus } from '$lib/stores/deviceStore.svelte';
  import { apiClient, type CANInterface } from '$lib/api/client';

  let interfaces = $state<CANInterface[]>([]);
  let selectedInterface = $state<CANInterface | null>(null);
  let bitrate = $state<number>(250000);
  let errorMsg = $state<string | null>(null);
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  const canStatus = $derived(deviceStore.canStatus);

  const statusLabel: Record<string, string> = {
    disconnected: 'Disconnected',
    connecting:   'Connecting…',
    claiming:     'Claiming…',
    claimed:      'Claimed',
    cannot_claim: 'Cannot Claim',
  };

  const statusColor: Record<string, string> = {
    disconnected:  'bg-gray-500',
    connecting:    'bg-yellow-500',
    claiming:      'bg-yellow-400 animate-pulse',
    claimed:       'bg-green-500',
    cannot_claim:  'bg-red-500',
  };

  // Poll /api/can/status every 500ms while in a transitional state so the
  // UI catches up even if a WebSocket broadcast is missed.
  function startPolling() {
    stopPolling();
    pollTimer = setInterval(async () => {
      const s = deviceStore.canStatus.state;
      if (s === 'connecting' || s === 'claiming') {
        await fetchCANStatus();
      } else {
        stopPolling();
      }
    }, 500);
  }

  function stopPolling() {
    if (pollTimer !== null) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  onMount(async () => {
    await fetchCANStatus();
    try {
      interfaces = await apiClient.listCANInterfaces();
      if (interfaces.length > 0) selectedInterface = interfaces[0];
    } catch (e) {
      console.error('Failed to load CAN interfaces:', e);
    }
  });

  onDestroy(() => stopPolling());

  async function handleConnect() {
    if (!selectedInterface) return;
    errorMsg = null;
    try {
      await connectCAN(selectedInterface.interface, selectedInterface.channel, bitrate);
      // Start polling while claiming so we don't rely solely on WS
      startPolling();
    } catch (e) {
      errorMsg = e instanceof Error ? e.message : 'Connection failed';
    }
  }

  async function handleDisconnect() {
    errorMsg = null;
    try {
      await disconnectCAN();
    } catch (e) {
      errorMsg = e instanceof Error ? e.message : 'Disconnect failed';
    }
  }

  // Monitor bus state
  let monitorChannel = $state('can1');
  let monitorBitrate = $state(250000);
  let monitorError = $state<string | null>(null);

  async function handleAddMonitor() {
    monitorError = null;
    try {
      await connectMonitorBus(monitorChannel.trim(), monitorBitrate);
    } catch (e) {
      monitorError = e instanceof Error ? e.message : 'Failed';
    }
  }
</script>

<div class="flex items-center gap-3 flex-wrap">
  <!-- Interface selector -->
  {#if canStatus.state === 'disconnected' || canStatus.state === 'cannot_claim'}
    <select
      class="bg-dark-card text-white border border-gray-600 rounded px-2 py-1 text-sm min-w-[180px]"
      bind:value={selectedInterface}
      disabled={interfaces.length === 0}
    >
      {#if interfaces.length === 0}
        <option value={null}>No interfaces found</option>
      {:else}
        {#each interfaces as iface}
          <option value={iface}>{iface.description}</option>
        {/each}
      {/if}
    </select>

    <input
      type="number"
      class="bg-dark-card text-white border border-gray-600 rounded px-2 py-1 text-sm w-28"
      placeholder="Bitrate"
      bind:value={bitrate}
      min={125000}
      max={1000000}
      step={125000}
    />

    <button
      class="px-3 py-1.5 rounded bg-green-700 hover:bg-green-600 text-white text-sm font-medium transition-colors disabled:opacity-50"
      onclick={handleConnect}
      disabled={!selectedInterface || deviceStore.isLoading}
    >
      Connect
    </button>
  {:else}
    <button
      class="px-3 py-1.5 rounded bg-red-700 hover:bg-red-600 text-white text-sm font-medium transition-colors"
      onclick={handleDisconnect}
      disabled={deviceStore.isLoading}
    >
      Disconnect
    </button>
  {/if}

  <!-- Status badge -->
  <div class="flex items-center gap-2">
    <div class="w-2.5 h-2.5 rounded-full {statusColor[canStatus.state] ?? 'bg-gray-500'}"></div>
    <span class="text-sm text-gray-300">{statusLabel[canStatus.state] ?? canStatus.state}</span>
  </div>

  {#if canStatus.address_claimed}
    <span class="text-xs text-gray-400 font-mono">
      SA: 0x{canStatus.sa.toString(16).toUpperCase().padStart(2, '0')}
      · {canStatus.interface}/{canStatus.channel}
    </span>
  {/if}

  {#if canStatus.state === 'cannot_claim'}
    <span class="text-xs text-red-400">Address contention — another node has higher priority for SA 0x{canStatus.sa.toString(16).toUpperCase()}</span>
  {/if}

  {#if errorMsg}
    <span class="text-xs text-red-400">{errorMsg}</span>
  {/if}

  <!-- Monitor Buses (shown when command bus is connected) -->
  {#if canStatus.state !== 'disconnected' && canStatus.state !== 'cannot_claim'}
    <div class="w-px h-5 bg-gray-600 hidden sm:block"></div>
    <span class="text-xs text-gray-500">Monitor:</span>
    <input
      type="text"
      placeholder="can1"
      bind:value={monitorChannel}
      class="bg-dark-card text-white border border-gray-700 rounded px-2 py-1 text-xs w-16 font-mono"
    />
    <button
      class="px-2 py-1 rounded bg-blue-800 hover:bg-blue-700 text-white text-xs transition-colors"
      onclick={handleAddMonitor}
      disabled={!monitorChannel.trim()}
    >
      + Add
    </button>
    {#each deviceStore.monitorChannels as ch (ch)}
      <span class="flex items-center gap-1 px-2 py-0.5 rounded bg-blue-900/40 border border-blue-700/50 text-xs font-mono text-blue-300">
        {ch}
        <button
          class="ml-0.5 text-blue-400 hover:text-red-400 transition-colors leading-none"
          onclick={() => disconnectMonitorBus(ch)}
          title="Remove monitor"
        >✕</button>
      </span>
    {/each}
    {#if monitorError}
      <span class="text-xs text-red-400">{monitorError}</span>
    {/if}
  {/if}
</div>
