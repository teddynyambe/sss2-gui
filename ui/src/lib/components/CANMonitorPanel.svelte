<script lang="ts">
  import { onMount } from 'svelte';
  import { deviceStore, addFrameForChannel, clearCorrelation, type ECUFrame } from '$lib/stores/deviceStore.svelte';

  const API_BASE = import.meta.env.VITE_API_BASE || '/api';

  let paused = $state(false);
  let saFilter = $state('');
  let selectedChannel = $state<string>('');

  // Channels with frames or actively monitored
  const availableChannels = $derived(
    [...new Set([
      ...Object.keys(deviceStore.framesByChannel),
      ...deviceStore.monitorChannels,
    ])].sort()
  );

  // Auto-select first available channel when selection is stale
  $effect(() => {
    if (availableChannels.length > 0 && !availableChannels.includes(selectedChannel)) {
      selectedChannel = availableChannels[0];
    }
  });

  // Live frames for the selected channel
  const channelFrames = $derived(deviceStore.framesByChannel[selectedChannel] ?? []);

  // Local snapshot for Pause support
  let displayedFrames = $state<ECUFrame[]>([]);

  $effect(() => {
    if (!paused) {
      displayedFrames = channelFrames;
    }
  });

  const filteredFrames = $derived(
    saFilter.trim() === ''
      ? displayedFrames
      : displayedFrames.filter(f =>
          f.sa.toUpperCase() === saFilter.trim().toUpperCase()
        )
  );

  // Sort correlated frames to the top
  const sortedFrames = $derived(
    filteredFrames.toSorted((a, b) => {
      const aC = !!deviceStore.correlatedFrames[a.arb_id];
      const bC = !!deviceStore.correlatedFrames[b.arb_id];
      return aC === bC ? 0 : aC ? -1 : 1;
    })
  );

  function clear() {
    displayedFrames = [];
  }

  function formatTime(ts: number): string {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString('en-US', { hour12: false }) +
      '.' + String(d.getMilliseconds()).padStart(3, '0');
  }

  onMount(async () => {
    // Fetch buffered history from can0 (command bus)
    try {
      const url = API_BASE.startsWith('http')
        ? `${API_BASE}/can/frames`
        : `${API_BASE}/can/frames`;
      const res = await fetch(url);
      if (res.ok) {
        const json = await res.json();
        for (const frame of (json.frames as ECUFrame[]).reverse()) {
          addFrameForChannel(frame.channel ?? 'can0', frame);
        }
      }
    } catch (e) {
      console.error('Failed to fetch ECU frames history:', e);
    }
  });
</script>

<div class="bg-dark-card rounded-lg p-4 mt-4">
  <!-- Channel tabs -->
  {#if availableChannels.length > 0}
    <div class="flex gap-1 mb-3 border-b border-dark-accent/50 -mx-4 px-4">
      {#each availableChannels as ch (ch)}
        {@const count = deviceStore.framesByChannel[ch]?.length ?? 0}
        <button
          class="px-3 py-1.5 text-xs font-mono rounded-t transition-colors border-b-2 {selectedChannel === ch
            ? 'border-blue-400 text-white bg-dark-accent/30'
            : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-dark-accent/20'}"
          onclick={() => { selectedChannel = ch; paused = false; }}
        >
          {ch}
          <span class="ml-1 text-gray-500">({count})</span>
        </button>
      {/each}
    </div>
  {/if}

  <!-- Header -->
  <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
    <h3 class="text-base font-semibold">
      ECU CAN Frame Monitor
      {#if selectedChannel && availableChannels.length <= 1}
        <span class="ml-2 text-xs text-gray-400 font-mono">{selectedChannel}</span>
      {/if}
    </h3>
    <div class="flex items-center gap-2 flex-wrap">
      <label class="text-sm text-gray-400" for="sa-filter">SA filter:</label>
      <input
        id="sa-filter"
        type="text"
        placeholder="e.g. 00"
        maxlength="2"
        bind:value={saFilter}
        class="w-16 px-2 py-1 text-xs bg-dark-bg border border-dark-accent rounded font-mono uppercase"
      />
      <button
        class="px-3 py-1 text-xs rounded border transition-colors {paused
          ? 'bg-yellow-600 border-yellow-500 hover:bg-yellow-700'
          : 'bg-dark-bg border-dark-accent hover:bg-dark-accent'}"
        onclick={() => (paused = !paused)}
      >
        {paused ? 'Resume' : 'Pause'}
      </button>
      <button
        class="px-3 py-1 text-xs rounded bg-dark-bg border border-dark-accent hover:bg-dark-accent transition-colors"
        onclick={clear}
      >
        Clear
      </button>
      {#if Object.keys(deviceStore.correlatedFrames).length > 0}
        <button
          class="px-3 py-1 text-xs rounded bg-orange-900/50 border border-orange-600/50 hover:bg-orange-800/50 text-orange-300 transition-colors"
          onclick={clearCorrelation}
          title="Clear correlation highlights"
        >
          Clear Correlation
        </button>
      {/if}
    </div>
  </div>

  <div class="overflow-auto max-h-72 rounded border border-dark-accent">
    <table class="w-full text-xs font-mono">
      <thead class="sticky top-0 bg-dark-card border-b border-dark-accent">
        <tr>
          <th class="text-left px-2 py-1 text-gray-400 whitespace-nowrap">Time</th>
          <th class="text-left px-2 py-1 text-gray-400">Arb ID</th>
          <th class="text-left px-2 py-1 text-gray-400">PGN</th>
          <th class="text-left px-2 py-1 text-gray-400">SA</th>
          <th class="text-left px-2 py-1 text-gray-400">Data</th>
        </tr>
      </thead>
      <tbody>
        {#if sortedFrames.length === 0}
          <tr>
            <td colspan="5" class="px-2 py-4 text-center text-gray-500">
              {#if !selectedChannel}
                No channel selected — connect a CAN bus above
              {:else if saFilter}
                No frames matching SA filter
              {:else}
                Waiting for frames on {selectedChannel}…
              {/if}
            </td>
          </tr>
        {:else}
          {#each sortedFrames as frame (frame._seq ?? frame.ts + frame.arb_id)}
            {@const changedSet = new Set(deviceStore.correlatedFrames[frame.arb_id] ?? [])}
            {@const isCorrelated = changedSet.size > 0}
            <tr
              class="border-b border-dark-bg hover:bg-dark-accent/20 transition-colors {isCorrelated ? 'bg-orange-950/30' : ''}"
            >
              <td class="px-2 py-0.5 text-gray-400 whitespace-nowrap">{formatTime(frame.ts)}</td>
              <td class="px-2 py-0.5 {isCorrelated ? 'text-orange-300' : 'text-blue-300'}">{frame.arb_id}</td>
              <td class="px-2 py-0.5 text-green-300">{frame.pgn}</td>
              <td class="px-2 py-0.5 text-yellow-300">{frame.sa}</td>
              <td class="px-2 py-0.5 tracking-wider">
                {#if isCorrelated}
                  {@const bytes = frame.data.match(/.{2}/g) ?? []}
                  <span class="font-mono text-xs">
                    {#each bytes as byte, i}
                      <span class={changedSet.has(i) ? 'text-red-400 font-bold' : 'text-gray-200'}>{byte}</span>{#if i < bytes.length - 1}<span class="text-gray-600"> </span>{/if}
                    {/each}
                  </span>
                {:else}
                  <span class="text-gray-200">{frame.data}</span>
                {/if}
              </td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>
  </div>

  <p class="text-right text-xs text-gray-500 mt-1">
    {sortedFrames.length} frame{sortedFrames.length !== 1 ? 's' : ''}
    {paused ? '· paused' : ''}
    {#if Object.keys(deviceStore.correlatedFrames).length > 0}
      · <span class="text-orange-400">{Object.keys(deviceStore.correlatedFrames).length} correlated</span>
    {/if}
  </p>
</div>
