<script lang="ts">
  import { onDestroy } from 'svelte';
  import type { PotentiometerDefinition, PotentiometerState } from '$lib/api/client';
  import { deviceStore, updateState } from '$lib/stores/deviceStore.svelte';

  // ✅ Using $props() rune for component props (Svelte 5)
  let { potDef, powerVoltage = '5V' }: { potDef: PotentiometerDefinition; powerVoltage?: '5V' | '12V' } = $props();
  
  let expanded = $state(false);
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let localWiperPosition = $state<number | null>(null);
  
  // ✅ Using $derived rune for reactive state
  const potState = $derived(deviceStore.deviceState?.potentiometers?.[potDef.id] as PotentiometerState | undefined);
  
  // Use local state for slider if available, otherwise use potState
  const displayWiperPosition = $derived(localWiperPosition ?? potState?.wiper_position ?? 0);
  
  // Get ECU pin configuration for this potentiometer's pin
  const ecuPinConfig = $derived(
    deviceStore.selectedECU?.pins?.[potDef.pin] || null
  );

  async function updatePot(updates: Partial<PotentiometerState>, debounce: boolean = false) {
    if (!potState) return;
    
    // Filter out application, wire_color, and old terminal fields from updates
    const { application, wire_color, term_a_connect, term_b_connect, wiper_connect, ...filteredUpdates } = updates as any;
    
    // If debouncing, clear previous timer and set new one
    if (debounce) {
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      
      debounceTimer = setTimeout(async () => {
        try {
          await updateState({
            potentiometers: {
              [potDef.id]: {
                ...potState,
                ...filteredUpdates
              }
            }
          });
          // Clear local state after successful update
          localWiperPosition = null;
        } catch (error) {
          // Silently handle timeout errors during slider movement
          // State is saved, hardware command is sent in background
          if (error instanceof Error && error.message.includes('timeout')) {
            console.log(`Potentiometer ${potDef.id} command queued (may timeout, but state saved)`);
          } else {
            console.error('Failed to update potentiometer:', error);
            // Only show alert for non-timeout errors
            alert('Failed to update potentiometer. Please try again.');
          }
        }
        debounceTimer = null;
      }, 300); // Wait 300ms after user stops moving slider
    } else {
      // Immediate update (for non-slider controls like checkboxes)
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
  }

  function toggleExpanded() {
    expanded = !expanded;
  }

  // ✅ Get voltage from state if available, otherwise calculate from wiper position
  // Voltage range depends on power setting: 0-5V or 0-12V
  const maxVoltage = $derived(powerVoltage === '12V' ? 12.0 : 5.0);
  const voltage = $derived(potState ? (potState.voltage ?? (potState.wiper_position / 255) * maxVoltage) : 0);
  const isEnabled = $derived(potState?.enabled ?? false);
  
  // Cleanup debounce timer on destroy
  onDestroy(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }
  });
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
        <div class="text-sm text-gray-400">{potState.wiper_position}</div>
      {/if}
      <div class="text-xl mt-1">{expanded ? '▲' : '▼'}</div>
    </div>
  </button>

  <!-- Expanded View -->
  {#if expanded && potState}
    <div class="border-t border-dark-accent/20 p-6 space-y-4">
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
          Wiper Position: {displayWiperPosition} ({((displayWiperPosition / 255) * maxVoltage).toFixed(2)}V)
        </label>
        <input
          id="wiper-position-{potDef.id}"
          type="range"
          min="0"
          max="255"
          value={localWiperPosition ?? displayWiperPosition}
          oninput={(e) => {
            const wiperPosition = parseInt(e.currentTarget.value, 10);
            const calculatedVoltage = (wiperPosition / 255) * maxVoltage;
            // Update local state immediately for UI responsiveness
            localWiperPosition = wiperPosition;
            e.currentTarget.style.setProperty('--val', String(wiperPosition));
            // Debounce the actual API call to avoid timeout errors from rapid updates
            updatePot({ wiper_position: wiperPosition, voltage: calculatedVoltage }, true);
          }}
          class="w-full mixer-slider"
          style={`--val:${localWiperPosition ?? displayWiperPosition}; --min:0; --max:255;`}
        />
        <div class="flex justify-between text-xs text-gray-400 mt-1">
          <span>0.0V</span>
          <span>{maxVoltage.toFixed(1)}V</span>
        </div>
      </div>

      <!-- On/Off Toggle -->
      <div>
        <div class="block text-sm text-gray-400 mb-2">Potentiometer State</div>
        <button
          class="w-full px-6 py-4 rounded font-semibold transition-colors min-h-touch"
          class:bg-green-600={isEnabled}
          class:hover:bg-green-700={isEnabled}
          class:bg-red-600={!isEnabled}
          class:hover:bg-red-700={!isEnabled}
          onclick={() => updatePot({ enabled: !isEnabled })}
        >
          {isEnabled ? 'On' : 'Off'}
        </button>
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
<style>
  .mixer-slider {
  /* variables you set from Svelte */
  --min: 0;
  --max: 255;
  --val: 0;

  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 46px;          /* input box height = thumb height */
  background: transparent;
  padding: 0;
  margin: 0;
  cursor: pointer;
}

/* ===== WebKit track with filled portion ===== */
.mixer-slider::-webkit-slider-runnable-track {
  height: 10px;           /* thin track */
  border-radius: 2px;
  background: linear-gradient(
    to right,
    #c9cdd1 0%,
    #60a5fa calc((var(--val) - var(--min)) * 100% / (var(--max) - var(--min))),
    #1f2937 calc((var(--val) - var(--min)) * 100% / (var(--max) - var(--min))),
    #1f2937 100%
  );
}

.mixer-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;

  width: 36px;
  height: 46px;
  border-radius: 8px;
  border: 2px solid #0f172a;
  margin-top: -22px;
  cursor: grab;
  padding: 10px;

  /* 🎛️ Base + vertical grooves */
  background:
    /* groove 1 */
    linear-gradient(
      to right,
      transparent 9px,
      rgba(15, 23, 42, 0.45) 10px,
      rgba(15, 23, 42, 0.45) 11px,
      transparent 12px
    ),
    /* groove 2 */
    linear-gradient(
      to right,
      transparent 15px,
      rgba(15, 23, 42, 0.45) 16px,
      rgba(15, 23, 42, 0.45) 17px,
      transparent 18px
    ),
    /* groove 3 */
    linear-gradient(
      to right,
      transparent 21px,
      rgba(15, 23, 42, 0.45) 22px,
      rgba(15, 23, 42, 0.45) 23px,
      transparent 24px
    ),
    #60a5fa; /* base thumb color */

  background-clip: padding-box;
  box-shadow: 0 6px 14px rgba(0,0,0,0.45);
}

/* ===== Firefox filled track support ===== */
.mixer-slider::-moz-range-track {
  height: 4px;
  background: #1f2937;
  border-radius: 2px;
}
.mixer-slider::-moz-range-progress {
  height: 10px;
  background: #60a5fa;
  border-radius: 2px;
}
.mixer-slider::-moz-range-thumb {
  width: 34px;
  height: 46px;
  background: #60a5fa;
  border-radius: 8px;
  border: 2px solid #0f172a;
  box-shadow: 0 6px 14px rgba(0,0,0,0.45);
}
</style>