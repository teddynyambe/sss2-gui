<script lang="ts">
  import type { PotentiometerDefinition, PotentiometerState } from '$lib/api/client';
  import { deviceStore, updateState, togglePinnedPot, togglePotMonitoring, startCorrelation } from '$lib/stores/deviceStore.svelte';

  // ✅ Using $props() rune for component props (Svelte 5)
  let { potDef, powerVoltage = '5V' }: { potDef: PotentiometerDefinition; powerVoltage?: '5V' | '12V' } = $props();

  let expanded = $state(false);
  let inflight = $state(false);
  let pendingWiper: number | null = null;
  let localWiperPosition = $state<number | null>(null);

  // ✅ Using $derived rune for reactive state
  const potState = $derived(deviceStore.deviceState?.potentiometers?.[potDef.id] as PotentiometerState | undefined);

  // Use local state for slider if available, otherwise use potState
  const displayWiperPosition = $derived(localWiperPosition ?? potState?.wiper_position ?? 0);

  // Get ECU pin configuration for this potentiometer's pin
  const ecuPinConfig = $derived(
    deviceStore.selectedECU?.pins?.[potDef.pin] || null
  );

  async function sendWiperUpdate(wiperPosition: number) {
    if (!potState) return;
    if (inflight) {
      pendingWiper = wiperPosition;
      return;
    }
    inflight = true;
    try {
      await updateState({
        potentiometers: {
          [potDef.id]: {
            ...potState,
            wiper_position: wiperPosition,
            voltage: (wiperPosition / 255) * maxVoltage,
          }
        }
      });
    } catch (error) {
      if (!(error instanceof Error && error.message.includes('timeout'))) {
        console.error('Failed to update potentiometer:', error);
      }
    } finally {
      inflight = false;
      localWiperPosition = null;
      if (pendingWiper !== null) {
        const next = pendingWiper;
        pendingWiper = null;
        sendWiperUpdate(next);
      }
    }
  }

  async function updatePot(updates: Partial<PotentiometerState>) {
    if (!potState) return;

    // Filter out application and wire_color from updates
    const { application, wire_color, ...filteredUpdates } = updates as any;

    try {
      await updateState({
        potentiometers: {
          [potDef.id]: {
            ...potState,
            ...filteredUpdates
          }
        }
      });
    } catch (error) {
      console.error('Failed to update potentiometer:', error);
      alert('Failed to update potentiometer. Please try again.');
    }
  }

  function toggleExpanded() {
    expanded = !expanded;
  }

  // ✅ Get voltage from state if available, otherwise calculate from wiper position
  // Voltage range depends on power setting: 0-5V or 0-12V
  const maxVoltage = $derived(powerVoltage === '12V' ? 12.0 : 5.0);
  const voltage = $derived(potState ? (potState.voltage ?? (potState.wiper_position / 255) * maxVoltage) : 0);
  const tcon = $derived(potState?.tcon ?? 0);
  const termA = $derived(!!(tcon & 4));
  const termWiper = $derived(!!(tcon & 2));
  const termB = $derived(!!(tcon & 1));
  const isEnabled = $derived(tcon === 7);
  // Parse resistance string like "10k" or "50k" into ohms
  const maxResistanceOhms = $derived(
    (() => { const m = potDef.resistance.match(/^(\d+(?:\.\d+)?)\s*k/i); return m ? parseFloat(m[1]) * 1000 : 10000; })()
  );
  const wiperResistance = $derived((displayWiperPosition / 255) * maxResistanceOhms);
  const isPinned = $derived(!!deviceStore.pinnedPotIds[potDef.id]);
  const isMonitored = $derived(deviceStore.monitoredPots.has(potDef.id));
</script>

<div class="bg-dark-card rounded-lg border border-dark-accent/20 overflow-hidden">
  <!-- Summary View -->
  <button
    class="w-full p-4 flex items-center justify-between hover:bg-dark-surface/50 transition-colors"
    onclick={toggleExpanded}
  >
    <div class="flex items-center gap-4">
      <div class="flex items-center gap-2">
        <!-- Status Indicator Circle -->
        <div
          class="w-4 h-4 rounded-full transition-colors"
          class:bg-green-500={isEnabled}
          class:bg-red-500={!isEnabled}
          title={isEnabled ? 'Potentiometer is ON' : 'Potentiometer is OFF'}
        ></div>
        <div class="bg-dark-accent text-dark-bg rounded px-3 py-1 font-bold">
          U{potDef.port}
        </div>
      </div>
      <div class="text-left">
        <div class="font-semibold">{potDef.name}</div>
        <div class="text-sm text-gray-400">{potDef.pin} • {potDef.resistance}</div>
      </div>
    </div>
    <div class="text-right">
      {#if potState}
        <div class="font-semibold">{voltage.toFixed(2)}V</div>
        <div class="text-sm text-gray-400">{potState.wiper_position} &middot; {wiperResistance >= 1000 ? (wiperResistance / 1000).toFixed(2) + 'k' : wiperResistance.toFixed(0)}&Omega;</div>
      {/if}
      <div class="text-xl mt-1">{expanded ? '▲' : '▼'}</div>
    </div>
  </button>

  <!-- Expanded View -->
  {#if expanded}
    <div class="border-t border-dark-accent/20 p-6 space-y-4">
      {#if !potState}
        <p class="text-sm text-yellow-400 italic">
          No device state loaded — connect to CAN and select an SSS2 node to control this potentiometer.
        </p>
      {/if}
      <!-- Dashboard Pin Toggle -->
      <div class="flex items-center justify-between">
        <span class="text-sm text-gray-400">Show on Dashboard</span>
        <button
          class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none"
          class:bg-blue-600={isPinned}
          class:bg-gray-600={!isPinned}
          style="min-height: unset; min-width: unset;"
          onclick={() => togglePinnedPot(potDef.id)}
          title={isPinned ? 'Remove from Dashboard' : 'Pin to Dashboard'}
        >
          <span
            class="inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform"
            class:translate-x-6={isPinned}
            class:translate-x-1={!isPinned}
          ></span>
        </button>
      </div>

      <!-- CAN Correlation Monitor Toggle -->
      <div class="flex items-center justify-between">
        <span class="text-sm text-gray-400">Monitor CAN Correlation</span>
        <button
          class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none"
          class:bg-orange-500={isMonitored}
          class:bg-gray-600={!isMonitored}
          style="min-height: unset; min-width: unset;"
          onclick={() => togglePotMonitoring(potDef.id)}
          title={isMonitored ? 'Stop monitoring CAN correlation' : 'Highlight CAN frames that change when slider moves'}
        >
          <span
            class="inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform"
            class:translate-x-6={isMonitored}
            class:translate-x-1={!isMonitored}
          ></span>
        </button>
      </div>

      <!-- Fixed Fields (Read-only) -->
      <div class="grid grid-cols-2 gap-4 text-sm">
        <div>
          <div class="text-gray-400">Pin</div>
          <div class="font-semibold">{potDef.pin}</div>
        </div>
        <div>
          <div class="text-gray-400">Port</div>
          <div class="font-semibold">{potDef.port}</div>
        </div>
        <div>
          <div class="text-gray-400">Resistance</div>
          <div class="font-semibold">{potDef.resistance}</div>
        </div>
        <div>
          <div class="text-gray-400">Fault Range</div>
          <div class="font-semibold">{potDef.ecm_fault_low}-{potDef.ecm_fault_high}</div>
        </div>
      </div>

      <!-- Wiper Position Slider -->
      <div>
        <label for="wiper-position-{potDef.id}" class="block text-sm text-gray-400 mb-2">
          Wiper Position: {displayWiperPosition} ({((displayWiperPosition / 255) * maxVoltage).toFixed(2)}V) — {wiperResistance >= 1000 ? (wiperResistance / 1000).toFixed(2) + 'k' : wiperResistance.toFixed(0)}&Omega;
        </label>
        <input
          id="wiper-position-{potDef.id}"
          type="range"
          min="0"
          max="255"
          value={localWiperPosition ?? displayWiperPosition}
          oninput={(e) => {
            const wiperPosition = parseInt(e.currentTarget.value, 10);
            localWiperPosition = wiperPosition;
            e.currentTarget.style.setProperty('--val', String(wiperPosition));
            if (deviceStore.monitoredPots.has(potDef.id)) startCorrelation();
            sendWiperUpdate(wiperPosition);
          }}
          class="w-full mixer-slider"
          style={`--val:${localWiperPosition ?? displayWiperPosition}; --min:0; --max:255;`}
        />
        <div class="flex justify-between text-xs text-gray-400 mt-1">
          <span>0.0V / 0&Omega;</span>
          <span>{maxVoltage.toFixed(1)}V / {potDef.resistance}&Omega;</span>
        </div>
      </div>

      <!-- Terminal Connections -->
      <div>
        <div class="block text-sm text-gray-400 mb-2">Terminal Connections</div>
        <div class="flex gap-4">
          <label class="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={termA}
              onchange={() => updatePot({ tcon: tcon ^ 4 })}
              class="w-5 h-5 rounded border-gray-500 bg-dark-surface text-blue-500 focus:ring-blue-500 cursor-pointer"
            />
            <span class="text-sm">A (5V)</span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={termWiper}
              onchange={() => updatePot({ tcon: tcon ^ 2 })}
              class="w-5 h-5 rounded border-gray-500 bg-dark-surface text-blue-500 focus:ring-blue-500 cursor-pointer"
            />
            <span class="text-sm">Wiper</span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={termB}
              onchange={() => updatePot({ tcon: tcon ^ 1 })}
              class="w-5 h-5 rounded border-gray-500 bg-dark-surface text-blue-500 focus:ring-blue-500 cursor-pointer"
            />
            <span class="text-sm">B (GND)</span>
          </label>
        </div>
      </div>

      <!-- ECU Function (Read-only from selected ECU) -->
      <div>
        <div class="text-sm text-gray-400 mb-1">ECU Function Description</div>
        <div class="px-4 py-2 rounded bg-dark-surface border border-dark-accent/20 text-gray-300 min-h-touch">
          {ecuPinConfig?.ecu_function || 'Not configured'}
        </div>
      </div>

      <!-- Wire Color (Read-only from selected ECU) -->
      <div>
        <div class="text-sm text-gray-400 mb-1">Wire Color</div>
        <div class="px-4 py-2 rounded bg-dark-surface border border-dark-accent/20 text-gray-300 min-h-touch">
          {ecuPinConfig?.wire_color || 'Not specified'}
        </div>
      </div>
    </div>
  {/if}
</div>
