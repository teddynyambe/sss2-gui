<script lang="ts">
  import { deviceStore, updateState, togglePinnedPot, togglePotMonitoring, startCorrelation } from '$lib/stores/deviceStore.svelte';
  import type { PotentiometerDefinition, PotentiometerState } from '$lib/api/client';

  const pinnedPotIds = $derived(deviceStore.pinnedPotIds);
  const allPots = $derived(deviceStore.catalog?.potentiometers ?? []);
  const pinnedPots = $derived(
    (allPots as PotentiometerDefinition[]).filter(p => !!pinnedPotIds[p.id])
  );

  let collapsed = $state(false);
  let localWipers = $state<Record<string, number>>({});
  const inflightPots: Record<string, boolean> = {};
  const pendingWipers: Record<string, number> = {};

  function potState(id: string): PotentiometerState | undefined {
    return deviceStore.deviceState?.potentiometers?.[id] as PotentiometerState | undefined;
  }

  function maxVoltage(portNum: number): number {
    const groupId = Math.ceil(portNum / 2);
    const pg = deviceStore.deviceState?.potentiometer_power_groups?.[`group_${groupId}`];
    return pg?.voltage_setting === '12V' ? 12.0 : 5.0;
  }

  function ecuFunction(pin: string): string {
    return deviceStore.selectedECU?.pins?.[pin]?.ecu_function ?? '';
  }

  function wiperPos(pot: PotentiometerDefinition): number {
    return localWipers[pot.id] ?? potState(pot.id)?.wiper_position ?? 0;
  }

  function voltageDisplay(pot: PotentiometerDefinition): string {
    const s = potState(pot.id);
    if (!s) return '—';
    const v = s.voltage ?? (wiperPos(pot) / 255) * maxVoltage(pot.port);
    return v.toFixed(2) + 'V';
  }

  async function sendWiperUpdate(pot: PotentiometerDefinition, raw: number) {
    if (inflightPots[pot.id]) {
      pendingWipers[pot.id] = raw;
      return;
    }
    const s = potState(pot.id);
    if (!s) return;
    inflightPots[pot.id] = true;
    const maxV = maxVoltage(pot.port);
    try {
      await updateState({
        potentiometers: { [pot.id]: { ...s, wiper_position: raw, voltage: (raw / 255) * maxV } }
      });
      const { [pot.id]: _, ...rest } = localWipers;
      localWipers = rest;
    } catch { /* ignore */ }
    inflightPots[pot.id] = false;
    if (pendingWipers[pot.id] !== undefined) {
      const next = pendingWipers[pot.id];
      delete pendingWipers[pot.id];
      sendWiperUpdate(pot, next);
    }
  }

  function handleSlider(pot: PotentiometerDefinition, raw: number) {
    const s = potState(pot.id);
    if (!s) return;
    localWipers = { ...localWipers, [pot.id]: raw };
    if (deviceStore.monitoredPots.has(pot.id)) startCorrelation();
    sendWiperUpdate(pot, raw);
  }

  function toggleTerminal(pot: PotentiometerDefinition, bit: number) {
    const s = potState(pot.id);
    if (!s) return;
    const newTcon = (s.tcon ?? 0) ^ bit;
    try {
      updateState({ potentiometers: { [pot.id]: { ...s, tcon: newTcon } } });
    } catch { /* ignore */ }
  }
</script>

{#if pinnedPots.length > 0}
  <div class="flex flex-shrink-0 self-start sticky top-0">
    {#if !collapsed}
      <div class="w-64 bg-dark-card rounded-l-lg overflow-y-auto max-h-[80vh] flex flex-col">
        <div class="px-3 pt-3 pb-1 flex items-center justify-between border-b border-gray-700/50">
          <span class="text-xs font-semibold text-gray-400 uppercase tracking-wide">Pinned Pots</span>
          <span class="text-xs text-gray-600">{pinnedPots.length}</span>
        </div>
        <div class="p-2 space-y-2 overflow-y-auto">
          {#each pinnedPots as pot (pot.id)}
            {@const s = potState(pot.id)}
            {@const wp = wiperPos(pot)}
            {@const tconVal = s?.tcon ?? 0}
            {@const enabled = tconVal === 7}
            {@const fn = ecuFunction(pot.pin)}
            <div class="bg-dark-surface rounded-lg p-2 space-y-1">
              <!-- Header row -->
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-1.5 min-w-0">
                  <div
                    class="w-2 h-2 rounded-full flex-shrink-0"
                    class:bg-green-500={enabled}
                    class:bg-red-500={!enabled}
                  ></div>
                  <div class="flex items-center gap-1 min-w-0">
                    <span class="bg-dark-accent text-dark-bg rounded px-1.5 py-0.5 text-xs font-bold flex-shrink-0">
                      U{pot.port}
                    </span>
                    <span class="text-xs text-gray-200 truncate">{pot.name}</span>
                  </div>
                </div>
                <div class="flex items-center gap-1.5 flex-shrink-0 ml-1">
                  <span class="text-xs font-mono text-gray-300">{voltageDisplay(pot)}</span>
                  <button
                    class="leading-none transition-colors"
                    class:text-orange-400={deviceStore.monitoredPots.has(pot.id)}
                    class:text-gray-600={!deviceStore.monitoredPots.has(pot.id)}
                    class:hover:text-orange-300={deviceStore.monitoredPots.has(pot.id)}
                    class:hover:text-gray-400={!deviceStore.monitoredPots.has(pot.id)}
                    style="min-height: unset; min-width: unset; padding: 2px; font-size: 10px;"
                    onclick={() => togglePotMonitoring(pot.id)}
                    title={deviceStore.monitoredPots.has(pot.id) ? 'Stop monitoring CAN correlation' : 'Monitor CAN correlation'}
                  >&#9208;</button>
                  <button
                    class="text-gray-600 hover:text-red-400 transition-colors leading-none"
                    style="min-height: unset; min-width: unset; padding: 2px;"
                    onclick={() => togglePinnedPot(pot.id)}
                    title="Unpin from Dashboard"
                  >✕</button>
                </div>
              </div>

              <!-- ECU function label -->
              {#if fn}
                <div class="text-xs text-blue-400 truncate px-0.5">{fn}</div>
              {/if}

              <!-- Slider -->
              {#if s}
                <div class="px-0.5">
                  <input
                    type="range"
                    min="0"
                    max="255"
                    value={wp}
                    oninput={(e) => handleSlider(pot, parseInt(e.currentTarget.value, 10))}
                    class="w-full mixer-slider"
                    style={`--val:${wp}; --min:0; --max:255;`}
                  />
                  <div class="flex justify-between text-xs text-gray-600 -mt-1">
                    <span>0</span>
                    <span class="text-gray-400 font-mono">{wp}</span>
                    <span>255</span>
                  </div>
                </div>

                <!-- Terminal checkboxes -->
                <div class="flex gap-2 justify-between">
                  <label class="flex items-center gap-1 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={!!(tconVal & 4)}
                      onchange={() => toggleTerminal(pot, 4)}
                      class="w-3.5 h-3.5 rounded border-gray-500 bg-dark-surface text-blue-500 cursor-pointer"
                      style="min-height: unset; min-width: unset;"
                    />
                    <span class="text-xs text-gray-400">A</span>
                  </label>
                  <label class="flex items-center gap-1 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={!!(tconVal & 2)}
                      onchange={() => toggleTerminal(pot, 2)}
                      class="w-3.5 h-3.5 rounded border-gray-500 bg-dark-surface text-blue-500 cursor-pointer"
                      style="min-height: unset; min-width: unset;"
                    />
                    <span class="text-xs text-gray-400">W</span>
                  </label>
                  <label class="flex items-center gap-1 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={!!(tconVal & 1)}
                      onchange={() => toggleTerminal(pot, 1)}
                      class="w-3.5 h-3.5 rounded border-gray-500 bg-dark-surface text-blue-500 cursor-pointer"
                      style="min-height: unset; min-width: unset;"
                    />
                    <span class="text-xs text-gray-400">B</span>
                  </label>
                </div>
              {:else}
                <p class="text-xs text-gray-600 italic">No state</p>
              {/if}
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <!-- Collapse / expand strip -->
    <button
      class="flex items-center justify-center bg-dark-accent/20 hover:bg-dark-accent/40 transition-colors rounded-r-lg w-6 flex-shrink-0 text-gray-500 hover:text-white"
      style="min-height: unset; min-width: unset;"
      onclick={() => collapsed = !collapsed}
      title={collapsed ? 'Expand' : 'Collapse'}
    >
      <span class="text-xs">{collapsed ? '›' : '‹'}</span>
    </button>
  </div>
{/if}
