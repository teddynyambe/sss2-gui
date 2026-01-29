<script lang="ts">
  import { onMount } from 'svelte';
  import { apiClient, type ECUFull, type PinConfiguration } from '$lib/api/client';
  import { deviceStore, reloadSelectedECU } from '$lib/stores/deviceStore.svelte';
  
  interface Props {
    ecuId?: string;
    allPins: string[];
    onSave: () => void;
    onCancel: () => void;
  }
  
  let { ecuId, allPins, onSave, onCancel }: Props = $props();
  
  let name = $state('');
  let model = $state('');
  let serialNumber = $state('');
  let pictures = $state<string[]>([]);
  let pictureUrl = $state('');
  let pins = $state<Record<string, PinConfiguration>>({});
  let loading = $state(false);
  let saving = $state(false);
  let error = $state<string | null>(null);
  
  // Track which pins are configured
  let configuredPins = $state<Set<string>>(new Set());
  // Track which pins are currently being edited
  let editingPins = $state<Set<string>>(new Set());
  
  async function loadECU() {
    if (!ecuId) return;
    
    loading = true;
    error = null;
    try {
      const ecu = await apiClient.getECU(ecuId);
      name = ecu.name;
      model = ecu.model;
      serialNumber = ecu.serial_number;
      pictures = ecu.pictures || [];
      pins = ecu.pins || {};
      configuredPins = new Set(Object.keys(pins));
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load ECU';
      console.error('Failed to load ECU:', err);
    } finally {
      loading = false;
    }
  }
  
  function addPinConfiguration(pin: string) {
    pins[pin] = { wire_color: '', ecu_function: '' };
    configuredPins = new Set([...configuredPins, pin]);
    // New pins start in edit mode
    editingPins = new Set([...editingPins, pin]);
  }
  
  function removePinConfiguration(pin: string) {
    delete pins[pin];
    const newConfiguredPins = new Set(configuredPins);
    newConfiguredPins.delete(pin);
    configuredPins = newConfiguredPins;
    
    const newEditingPins = new Set(editingPins);
    newEditingPins.delete(pin);
    editingPins = newEditingPins;
  }
  
  function startEditing(pin: string) {
    editingPins = new Set([...editingPins, pin]);
  }
  
  function stopEditing(pin: string) {
    const newSet = new Set(editingPins);
    newSet.delete(pin);
    editingPins = newSet;
  }
  
  function savePinConfiguration(pin: string) {
    // Values are already saved via bind:value, just exit edit mode
    stopEditing(pin);
  }
  
  function addPicture() {
    if (pictureUrl.trim()) {
      pictures = [...pictures, pictureUrl.trim()];
      pictureUrl = '';
    }
  }
  
  function removePicture(index: number) {
    pictures = pictures.filter((_, i) => i !== index);
  }
  
  async function handleSave() {
    if (!name.trim()) {
      error = 'ECU name is required';
      return;
    }
    
    saving = true;
    error = null;
    
    try {
      let savedECUId = ecuId;
      if (ecuId) {
        // Update existing
        await apiClient.updateECU(ecuId, {
          name: name.trim(),
          model: model.trim(),
          serial_number: serialNumber.trim(),
          pictures,
          pins
        });
      } else {
        // Create new
        const newECU = await apiClient.createECU({
          name: name.trim(),
          model: model.trim(),
          serial_number: serialNumber.trim(),
          pictures,
          pins
        });
        savedECUId = newECU.id;
      }
      
      // If the saved ECU is currently selected, reload it to get latest changes
      if (savedECUId && deviceStore.selectedECUId === savedECUId) {
        await reloadSelectedECU();
      }
      
      onSave();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to save ECU';
      console.error('Failed to save ECU:', err);
    } finally {
      saving = false;
    }
  }
  
  onMount(() => {
    if (ecuId) {
      loadECU();
    }
  });
</script>

<div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 overflow-y-auto py-8" role="dialog" aria-modal="true" onclick={onCancel} onkeydown={(e) => e.key === 'Escape' && onCancel()}>
  <div class="bg-dark-card rounded-lg border border-dark-accent/20 p-6 max-w-4xl w-full mx-4 my-8 max-h-[90vh] overflow-y-auto" onclick={(e) => e.stopPropagation()} role="document" >
    <div class="flex items-center justify-between mb-6">
      <h3 class="text-2xl font-semibold">{ecuId ? 'Edit ECU' : 'Add New ECU'}</h3>
      <button
        class="px-4 py-2 rounded bg-dark-surface hover:bg-dark-surface/80 text-white font-semibold transition-colors min-h-touch"
        onclick={onCancel}
      >
        ✕
      </button>
    </div>
    
    {#if error}
      <div class="p-4 rounded bg-red-900/30 border border-red-500 text-red-200 mb-4">
        {error}
      </div>
    {/if}
    
    {#if loading}
      <div class="text-center py-8 text-gray-400">Loading ECU...</div>
    {:else}
      <div class="space-y-6">
        <!-- Basic Info -->
        <div class="space-y-4">
          <h4 class="text-lg font-semibold border-b border-dark-accent/20 pb-2">Basic Information</h4>
          
          <div>
            <label for="ecu-name" class="block text-sm text-gray-400 mb-2">ECU Name *</label>
            <input
              id="ecu-name"
              type="text"
              bind:value={name}
              placeholder="e.g., ECM-123"
              class="w-full px-4 py-3 rounded bg-dark-surface border border-dark-accent/20 focus:border-dark-accent focus:outline-none min-h-touch"
            />
          </div>
          
          <div>
            <label for="ecu-model" class="block text-sm text-gray-400 mb-2">Model</label>
            <input
              id="ecu-model"
              type="text"
              bind:value={model}
              placeholder="e.g., Model XYZ"
              class="w-full px-4 py-3 rounded bg-dark-surface border border-dark-accent/20 focus:border-dark-accent focus:outline-none min-h-touch"
            />
          </div>
          
          <div>
            <label for="ecu-serial" class="block text-sm text-gray-400 mb-2">Serial Number</label>
            <input
              id="ecu-serial"
              type="text"
              bind:value={serialNumber}
              placeholder="e.g., SN123456"
              class="w-full px-4 py-3 rounded bg-dark-surface border border-dark-accent/20 focus:border-dark-accent focus:outline-none min-h-touch"
            />
          </div>
        </div>
        
        <!-- Pictures -->
        <div class="space-y-4">
          <h4 class="text-lg font-semibold border-b border-dark-accent/20 pb-2">Pictures</h4>
          
          <div class="flex gap-2">
            <input
              type="text"
              bind:value={pictureUrl}
              placeholder="Picture URL or file path"
              class="flex-1 px-4 py-3 rounded bg-dark-surface border border-dark-accent/20 focus:border-dark-accent focus:outline-none min-h-touch"
              onkeydown={(e) => e.key === 'Enter' && addPicture()}
            />
            <button
              class="px-6 py-3 rounded bg-dark-accent hover:bg-dark-accent/80 text-dark-bg font-semibold transition-colors min-h-touch"
              onclick={addPicture}
            >
              Add
            </button>
          </div>
          
          {#if pictures.length > 0}
            <div class="space-y-2">
              {#each pictures as picture, index (index)}
                <div class="flex items-center gap-2 p-2 bg-dark-surface rounded">
                  <span class="flex-1 text-sm truncate">{picture}</span>
                  <button
                    class="px-3 py-1 rounded bg-red-600 hover:bg-red-700 text-white text-sm font-semibold transition-colors min-h-touch"
                    onclick={() => removePicture(index)}
                  >
                    Remove
                  </button>
                </div>
              {/each}
            </div>
          {/if}
        </div>
        
        <!-- Pin Configurations -->
        <div class="space-y-4">
          <h4 class="text-lg font-semibold border-b border-dark-accent/20 pb-2">Pin Configurations</h4>
          
          <!-- Add Pin Button -->
          <div>
            <select
              class="w-full px-4 py-3 rounded bg-dark-surface border border-dark-accent/20 focus:border-dark-accent focus:outline-none min-h-touch"
              onchange={(e) => {
                const pin = e.currentTarget.value;
                if (pin && !configuredPins.has(pin)) {
                  addPinConfiguration(pin);
                  e.currentTarget.value = '';
                }
              }}
            >
              <option value="">Select a pin to configure...</option>
              {#each allPins as pin}
                {#if !configuredPins.has(pin)}
                  <option value={pin}>{pin}</option>
                {/if}
              {/each}
            </select>
          </div>
          
          <!-- Configured Pins -->
          {#if Object.keys(pins).length > 0}
            <div class="space-y-4 border border-dark-accent/20 rounded-lg p-4">
              {#each Object.entries(pins) as [pin, config]}
                {#if editingPins.has(pin)}
                  <!-- Edit Mode -->
                  <div class="bg-dark-surface rounded-lg p-4 space-y-3">
                    <div class="flex items-center justify-between">
                      <h5 class="font-semibold text-lg">{pin}</h5>
                      <button
                        class="px-4 py-2 rounded bg-dark-accent hover:bg-dark-accent/80 text-dark-bg font-semibold transition-colors min-h-touch"
                        onclick={() => savePinConfiguration(pin)}
                      >
                        Save
                      </button>
                    </div>
                    
                    <div>
                      <label for="wire-color-{pin}" class="block text-sm text-gray-400 mb-2">Wire Color</label>
                      <input
                        id="wire-color-{pin}"
                        type="text"
                        bind:value={pins[pin].wire_color}
                        placeholder="e.g., PPL/WHT, Red/White"
                        class="w-full px-4 py-3 rounded bg-dark-bg border border-dark-accent/20 focus:border-dark-accent focus:outline-none min-h-touch"
                      />
                    </div>
                    
                    <div>
                      <label for="ecu-function-{pin}" class="block text-sm text-gray-400 mb-2">ECU Function Description</label>
                      <textarea
                        id="ecu-function-{pin}"
                        bind:value={pins[pin].ecu_function}
                        placeholder="Describe the expected function of this wire from the ECU perspective"
                        rows="2"
                        class="w-full px-4 py-3 rounded bg-dark-bg border border-dark-accent/20 focus:border-dark-accent focus:outline-none min-h-touch"
                      ></textarea>
                    </div>
                  </div>
                {:else}
                  <!-- View Mode -->
                  <div class="bg-dark-surface rounded-lg p-4 space-y-3">
                    <div class="flex items-center justify-between">
                      <h5 class="font-semibold text-lg">{pin}</h5>
                      <div class="flex gap-2">
                        <button
                          class="px-4 py-2 rounded bg-blue-600 hover:bg-blue-700 text-white font-semibold transition-colors min-h-touch"
                          onclick={() => startEditing(pin)}
                        >
                          Edit
                        </button>
                        <button
                          class="px-4 py-2 rounded bg-red-600 hover:bg-red-700 text-white font-semibold transition-colors min-h-touch"
                          onclick={() => removePinConfiguration(pin)}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                    
                    <div class="space-y-2 text-sm">
                      <div>
                        <span class="text-gray-400">Wire Color:</span>
                        <span class="ml-2 font-semibold">{config.wire_color || 'Not specified'}</span>
                      </div>
                      <div>
                        <span class="text-gray-400">ECU Function:</span>
                        <div class="ml-2 mt-1 text-gray-300">{config.ecu_function || 'Not specified'}</div>
                      </div>
                    </div>
                  </div>
                {/if}
              {/each}
            </div>
          {/if}
        </div>
        
        <!-- Actions -->
        <div class="flex gap-4 justify-end pt-4 border-t border-dark-accent/20">
          <button
            class="px-6 py-3 rounded bg-dark-surface hover:bg-dark-surface/80 text-white font-semibold transition-colors min-h-touch"
            onclick={onCancel}
            disabled={saving}
          >
            Cancel
          </button>
          <button
            class="px-6 py-3 rounded bg-dark-accent hover:bg-dark-accent/80 text-dark-bg font-semibold transition-colors min-h-touch disabled:opacity-50"
            onclick={handleSave}
            disabled={saving || !name.trim()}
          >
            {saving ? 'Saving...' : 'Save ECU'}
          </button>
        </div>
      </div>
    {/if}
  </div>
</div>

<style>
  .bg-dark-card.rounded-lg.border.border-dark-accent\/20.p-6.max-w-4xl.w-full.mx-4.my-8.max-h-\[90vh\].overflow-y-auto {
    background-color: #083402!important;
  }
</style>
