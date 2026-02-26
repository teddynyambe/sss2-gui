<script lang="ts">
  import { deviceStore, scanCANNodes, selectSSS2, setMonitoredECU } from '$lib/stores/deviceStore.svelte';

  const canStatus = $derived(deviceStore.canStatus);
  const nodes = $derived(deviceStore.discoveredNodes);
  const connectedSA = $derived(deviceStore.connectedSSS2SA);
  const monitoredSA = $derived(deviceStore.monitoredECUSA);

  let isScanning = $state(false);
  let errorMsg = $state<string | null>(null);
  let manualSA = $state('0x80');
  let isConnecting = $state(false);

  const nodeList = $derived(Object.values(nodes).sort((a, b) => a.sa - b.sa));

  async function handleScan() {
    isScanning = true;
    errorMsg = null;
    try {
      await scanCANNodes();
    } catch (e) {
      errorMsg = e instanceof Error ? e.message : 'Scan failed';
    } finally {
      isScanning = false;
    }
  }

  async function handleSelectSSS2(sa: number) {
    errorMsg = null;
    try {
      await selectSSS2(sa);
    } catch (e) {
      errorMsg = e instanceof Error ? e.message : 'Failed to fetch state';
    }
  }

  async function handleManualConnect() {
    const sa = parseInt(manualSA, 16);
    if (isNaN(sa) || sa < 0 || sa > 0xFE) {
      errorMsg = 'Invalid SA (expected 0x00–0xFE)';
      return;
    }
    isConnecting = true;
    errorMsg = null;
    try {
      await selectSSS2(sa);
    } catch (e) {
      errorMsg = e instanceof Error ? e.message : 'Failed to connect';
    } finally {
      isConnecting = false;
    }
  }

  function saHex(sa: number): string {
    return '0x' + sa.toString(16).toUpperCase().padStart(2, '0');
  }

  function shortMfr(name: string): string {
    // Strip "(formerly ...)" and "(f/k/a ...)" suffixes for display brevity
    return name.replace(/\s*\(formerly[^)]*\)/i, '').replace(/\s*\(f\/k\/a[^)]*\)/i, '').trim();
  }
</script>

<div class="flex flex-col gap-3">
  <div class="flex items-center gap-3">
    <span class="text-sm font-medium text-gray-300">J1939 Network</span>
    <button
      class="px-3 py-1.5 rounded bg-blue-700 hover:bg-blue-600 text-white text-sm font-medium transition-colors disabled:opacity-50"
      onclick={handleScan}
      disabled={!canStatus.address_claimed || isScanning}
    >
      {isScanning ? 'Scanning…' : 'Scan Network'}
    </button>
    {#if errorMsg}
      <span class="text-xs text-red-400">{errorMsg}</span>
    {/if}
  </div>

  {#if nodeList.length > 0}
    <table class="w-full text-sm border-collapse">
      <thead>
        <tr class="text-left text-gray-400 border-b border-gray-700">
          <th class="py-1 pr-4 font-medium">SA</th>
          <th class="py-1 pr-4 font-medium">NAME</th>
          <th class="py-1 pr-4 font-medium">Type</th>
          <th class="py-1 font-medium">Action</th>
        </tr>
      </thead>
      <tbody>
        {#each nodeList as node}
          <tr
            class="border-b border-gray-800 {node.is_sss2 ? 'bg-green-900/20' : ''} {connectedSA === node.sa ? 'bg-green-800/30' : ''}"
          >
            <td class="py-1.5 pr-4 font-mono text-gray-200">{saHex(node.sa)}</td>
            <td class="py-1.5 pr-4">
              <div class="font-mono text-gray-400 text-xs">{node.name_hex}</div>
              {#if node.manufacturer}
                <div class="text-gray-500 text-xs mt-0.5">{shortMfr(node.manufacturer)}</div>
              {/if}
            </td>
            <td class="py-1.5 pr-4">
              {#if node.is_sss2}
                <span class="px-1.5 py-0.5 rounded text-xs bg-green-700 text-white">SSS2</span>
              {:else if node.label}
                <span class="text-gray-300 text-xs">{node.label}</span>
              {:else}
                <span class="text-gray-500 text-xs">Other</span>
              {/if}
            </td>
            <td class="py-1.5">
              {#if node.is_sss2}
                {#if connectedSA === node.sa}
                  <span class="text-xs text-green-400 font-medium">Active</span>
                {:else}
                  <button
                    class="px-2 py-0.5 rounded bg-green-700 hover:bg-green-600 text-white text-xs transition-colors"
                    onclick={() => handleSelectSSS2(node.sa)}
                    disabled={deviceStore.isLoading}
                  >
                    Use this SSS2
                  </button>
                {/if}
              {:else}
                {#if monitoredSA === node.sa}
                  <span class="text-xs text-blue-400 font-medium">Monitored</span>
                {:else}
                  <button
                    class="px-2 py-0.5 rounded bg-blue-700 hover:bg-blue-600 text-white text-xs transition-colors"
                    onclick={() => setMonitoredECU(node.sa)}
                  >Monitor ECU</button>
                {/if}
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {:else if canStatus.address_claimed}
    <p class="text-sm text-gray-500 italic">No nodes discovered. Click "Scan Network" to search.</p>
  {:else}
    <p class="text-sm text-gray-500 italic">Connect to a CAN interface first.</p>
  {/if}

  {#if canStatus.address_claimed}
    <div class="flex items-center gap-2 pt-1 border-t border-gray-800">
      <span class="text-xs text-gray-500">Connect to SSS2 by SA:</span>
      <input
        type="text"
        bind:value={manualSA}
        placeholder="0x80"
        class="w-20 px-2 py-0.5 rounded bg-gray-800 border border-gray-700 text-xs font-mono text-gray-200 focus:outline-none focus:border-green-600"
      />
      <button
        class="px-2 py-0.5 rounded bg-green-700 hover:bg-green-600 text-white text-xs transition-colors disabled:opacity-50"
        onclick={handleManualConnect}
        disabled={isConnecting || deviceStore.isLoading}
      >
        {#if isConnecting}
          Connecting…
        {:else if connectedSA !== null && connectedSA === parseInt(manualSA, 16)}
          Active
        {:else}
          Connect
        {/if}
      </button>
    </div>
  {/if}
</div>
