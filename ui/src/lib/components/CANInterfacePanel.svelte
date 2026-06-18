<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { apiClient, type IfaceState } from '$lib/api/client';

  let interfaces = $state<IfaceState[]>([]);
  let busy = $state<Record<string, boolean>>({});
  let errorMsg = $state<string | null>(null);
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  async function refresh() {
    try {
      const status = await apiClient.getCANInterfaceStatus();
      interfaces = status.interfaces;
    } catch (e) {
      errorMsg = e instanceof Error ? e.message : 'Failed to read CAN interfaces';
    }
  }

  async function toggle(iface: IfaceState) {
    errorMsg = null;
    busy = { ...busy, [iface.name]: true };
    try {
      if (iface.up) await apiClient.canInterfaceDown(iface.name);
      else await apiClient.canInterfaceUp(iface.name);
      await refresh();
    } catch (e) {
      errorMsg = e instanceof Error ? e.message : `Failed to toggle ${iface.name}`;
    } finally {
      busy = { ...busy, [iface.name]: false };
    }
  }

  onMount(() => {
    refresh();
    pollTimer = setInterval(refresh, 4000);
  });
  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer);
  });
</script>

<div class="bg-dark-card rounded-lg p-4 mb-4">
  <div class="flex items-center justify-between mb-3">
    <h3 class="text-base font-semibold">CAN Interfaces (SocketCAN)</h3>
    <button
      class="text-xs text-gray-400 hover:text-white transition-colors min-h-touch px-2"
      onclick={refresh}
    >
      ⟳ Refresh
    </button>
  </div>

  {#if interfaces.length === 0}
    <p class="text-sm text-gray-500">No controllable interfaces reported.</p>
  {/if}

  <div class="grid gap-2 sm:grid-cols-2">
    {#each interfaces as iface (iface.name)}
      <div class="flex items-center justify-between rounded border border-gray-700 px-3 py-2">
        <div class="flex items-center gap-2">
          <span
            class="w-3 h-3 rounded-full {iface.up
              ? 'bg-green-500'
              : iface.present
                ? 'bg-gray-500'
                : 'bg-red-600'}"
            title={iface.present ? (iface.up ? 'up' : 'down') : 'not present'}
          ></span>
          <span class="font-mono text-sm">{iface.name}</span>
          <span class="text-xs text-gray-400">
            {#if !iface.present}
              not present
            {:else if iface.up}
              up{iface.bitrate ? ` · ${(iface.bitrate / 1000).toFixed(0)}k` : ''}
            {:else}
              down
            {/if}
          </span>
        </div>

        <button
          class="px-3 py-1.5 rounded text-sm font-medium min-h-touch transition-colors disabled:opacity-50
            {iface.up
            ? 'bg-red-700 hover:bg-red-600'
            : 'bg-green-700 hover:bg-green-600'}"
          onclick={() => toggle(iface)}
          disabled={!iface.present || busy[iface.name]}
        >
          {busy[iface.name] ? '…' : iface.up ? 'Stop' : 'Start'}
        </button>
      </div>
    {/each}
  </div>

  {#if errorMsg}
    <p class="text-xs text-red-400 mt-3">{errorMsg}</p>
  {/if}
</div>
