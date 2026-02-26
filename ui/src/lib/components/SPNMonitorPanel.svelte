<script lang="ts">
  import { deviceStore, setMonitoredECU } from '$lib/stores/deviceStore.svelte';

  const rows = $derived(
    Object.values(deviceStore.spnValues).sort((a, b) => a.label.localeCompare(b.label))
  );
  const unknownRows = $derived(
    Object.values(deviceStore.unknownFrames).sort((a, b) =>
      parseInt(a.pgn, 16) - parseInt(b.pgn, 16)
    )
  );
  const monSA = $derived(deviceStore.monitoredECUSA);
  const saHex = $derived(monSA !== null ? '0x' + monSA.toString(16).toUpperCase().padStart(2, '0') : '');

  let unknownExpanded = $state(true);

  function fmt(v: number): string {
    return parseFloat(v.toFixed(2)).toString();
  }

  function fmtSpec(v: number | null): string {
    return v === null ? '—' : fmt(v);
  }

  // Format hex data bytes with spaces: "DC0001FF" → "DC 00 01 FF"
  function fmtData(hex: string): string {
    return hex.match(/.{1,2}/g)?.join(' ') ?? hex;
  }

  function pgnDec(pgn: string): number {
    return parseInt(pgn, 16);
  }
</script>

<div class="bg-dark-card rounded-lg p-4">
  <div class="flex items-center justify-between mb-3">
    <h3 class="text-base font-semibold">
      ECU Parameter Monitor
      {#if monSA !== null}
        <span class="ml-2 text-xs text-blue-300 font-mono">{saHex}</span>
      {/if}
    </h3>
    <button
      onclick={() => setMonitoredECU(null)}
      class="text-xs text-gray-500 hover:text-gray-300 transition-colors"
    >
      Stop monitoring
    </button>
  </div>

  <!-- ── Identified parameters ── -->
  {#if rows.length === 0}
    <p class="text-sm text-gray-500 italic">Waiting for ECU data…</p>
  {:else}
    <div class="overflow-auto max-h-[50vh]">
      <table class="w-full text-sm border-collapse">
        <thead class="sticky top-0 bg-dark-card">
          <tr class="text-left text-gray-400 border-b border-gray-700">
            <th class="py-1.5 pr-6 font-medium">Parameter</th>
            <th class="py-1.5 pr-4 font-medium text-right">Value</th>
            <th class="py-1.5 pr-6 font-medium">Units</th>
            <th class="py-1.5 pr-4 font-medium text-right">Spec Min</th>
            <th class="py-1.5 font-medium text-right">Spec Max</th>
          </tr>
        </thead>
        <tbody>
          {#each rows as row (row.spn)}
            <tr class="border-b border-gray-800 hover:bg-gray-800/30 transition-colors">
              <td class="py-1.5 pr-6 text-gray-200">
                {row.label}
                <span class="ml-1.5 text-xs text-gray-500">[SPN {row.spn} · PGN {row.pgn}]</span>
              </td>
              <td class="py-1.5 pr-4 text-right font-mono text-white">{fmt(row.value)}</td>
              <td class="py-1.5 pr-6 text-gray-400">{row.unit}</td>
              <td class="py-1.5 pr-4 text-right font-mono text-gray-500">{fmtSpec(row.spec_min)}</td>
              <td class="py-1.5 text-right font-mono text-gray-500">{fmtSpec(row.spec_max)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <p class="text-right text-xs text-gray-500 mt-1">
      {rows.length} parameter{rows.length !== 1 ? 's' : ''}
    </p>
  {/if}

  <!-- ── Unidentified messages ── -->
  {#if unknownRows.length > 0}
    <div class="mt-4 border-t border-gray-700/50 pt-3">
      <button
        class="flex items-center gap-2 text-xs font-semibold text-gray-400 hover:text-gray-200 transition-colors mb-2 w-full text-left"
        style="min-height: unset; min-width: unset;"
        onclick={() => unknownExpanded = !unknownExpanded}
      >
        <span>{unknownExpanded ? '▾' : '▸'}</span>
        <span>Unidentified Messages</span>
        <span class="ml-1 px-1.5 py-0.5 rounded-full bg-gray-700 text-gray-400 font-mono">
          {unknownRows.length}
        </span>
      </button>

      {#if unknownExpanded}
        <div class="overflow-auto max-h-48">
          <table class="w-full text-xs border-collapse font-mono">
            <thead class="sticky top-0 bg-dark-card">
              <tr class="text-left text-gray-500 border-b border-gray-700">
                <th class="py-1 pr-4 font-medium">PGN</th>
                <th class="py-1 pr-4 font-medium">Arb ID</th>
                <th class="py-1 pr-4 font-medium">Data</th>
                <th class="py-1 text-right font-medium">Seen</th>
              </tr>
            </thead>
            <tbody>
              {#each unknownRows as row (row.pgn)}
                <tr class="border-b border-gray-800/50 hover:bg-gray-800/20 transition-colors">
                  <td class="py-1 pr-4 text-yellow-400">
                    {row.pgn}
                    <span class="text-gray-600 ml-1">({pgnDec(row.pgn)})</span>
                  </td>
                  <td class="py-1 pr-4 text-gray-400">{row.arb_id}</td>
                  <td class="py-1 pr-4 text-gray-300 tracking-wide">{fmtData(row.data)}</td>
                  <td class="py-1 text-right text-gray-500">{row.count}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
        <p class="text-right text-xs text-gray-600 mt-1">
          PGNs not yet in J1939DA — use data bytes to identify
        </p>
      {/if}
    </div>
  {/if}
</div>
