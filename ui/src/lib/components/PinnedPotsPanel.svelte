<script lang="ts">
  import { onDestroy } from 'svelte';
  import { deviceStore, updateState, togglePinnedPot } from '$lib/stores/deviceStore.svelte';
  import type { PotentiometerDefinition, PotentiometerState } from '$lib/api/client';

  const pinnedPotIds = $derived(deviceStore.pinnedPotIds);
  const allPots = $derived(deviceStore.catalog?.potentiometers ?? []);
  const pinnedPots = $derived(
    (allPots as PotentiometerDefinition[]).filter(p => !!pinnedPotIds[p.id])
  );

  let collapsed = $state(false);
  let localWipers = $state<Record<string, number>>({});
  const debounceTimers: Record<string, ReturnType<typeof setTimeout>> = {};

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

  function handleSlider(pot: PotentiometerDefinition, raw: number) {
    const s = potState(pot.id);
    if (!s) return;
    localWipers = { ...localWipers, [pot.id]: raw };
    if (debounceTimers[pot.id]) clearTimeout(debounceTimers[pot.id]);
    debounceTimers[pot.id] = setTimeout(async () => {
      const maxV = maxVoltage(pot.port);
      try {
        await updateState({
          potentiometers: { [pot.id]: { ...s, wiper_position: raw, voltage: (raw / 255) * maxV } }
        });
        const { [pot.id]: _, ...rest } = localWipers;
        localWipers = rest;
      } catch { /* ignore */ }
      delete debounceTimers[pot.id];
    }, 300);
  }

  async function toggleEnabled(pot: PotentiometerDefinition) {
    const s = potState(pot.id);
    if (!s) return;
    try {
      await updateState({ potentiometers: { [pot.id]: { ...s, enabled: !s.enabled } } });
    } catch { /* ignore */ }
  }

  onDestroy(() => {
    Object.values(debounceTimers).forEach(t => clearTimeout(t));
  });
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
            {@const enabled = s?.enabled ?? false}
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

                <!-- On/Off button -->
                <button
                  class="w-full py-0.5 rounded text-xs font-semibold transition-colors"
                  style="min-height: unset;"
                  class:bg-green-700={enabled}
                  class:hover:bg-green-600={enabled}
                  class:bg-red-800={!enabled}
                  class:hover:bg-red-700={!enabled}
                  onclick={() => toggleEnabled(pot)}
                >{enabled ? 'On' : 'Off'}</button>
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
