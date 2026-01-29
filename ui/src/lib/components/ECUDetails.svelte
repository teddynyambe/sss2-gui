<script lang="ts">
  import { onMount } from 'svelte';
  import { apiClient, type ECUFull } from '$lib/api/client';
  
  interface Props {
    ecuId: string;
  }
  
  let { ecuId }: Props = $props();
  
  let ecu = $state<ECUFull | null>(null);
  let loading = $state(false);
  let error = $state<string | null>(null);
  
  async function loadECU() {
    loading = true;
    error = null;
    try {
      ecu = await apiClient.getECU(ecuId);
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load ECU';
      console.error('Failed to load ECU:', err);
    } finally {
      loading = false;
    }
  }
  
  onMount(() => {
    loadECU();
  });
</script>

{#if loading}
  <div class="text-center py-8 text-gray-400">Loading ECU details...</div>
{:else if error}
  <div class="p-4 rounded bg-red-900/30 border border-red-500 text-red-200">
    {error}
  </div>
{:else if ecu}
  <div class="bg-dark-card rounded-lg border border-dark-accent/20 p-6 space-y-6" style="background-color: #1f2937!important;">
    <h4 class="text-xl font-semibold border-b border-dark-accent/20 pb-2">ECU Details</h4>
    
    <!-- Basic Info -->
    <div class="grid grid-cols-2 gap-4">
      <div>
        <div class="text-sm text-gray-400">Name</div>
        <div class="font-semibold text-lg">{ecu.name}</div>
      </div>
      {#if ecu.model}
        <div>
          <div class="text-sm text-gray-400">Model</div>
          <div class="font-semibold">{ecu.model}</div>
        </div>
      {/if}
      {#if ecu.serial_number}
        <div>
          <div class="text-sm text-gray-400">Serial Number</div>
          <div class="font-semibold">{ecu.serial_number}</div>
        </div>
      {/if}
    </div>
    
    <!-- Pictures -->
    {#if ecu.pictures && ecu.pictures.length > 0}
      <div>
        <div class="text-sm text-gray-400 mb-2">Pictures</div>
        <div class="space-y-2">
          {#each ecu.pictures as picture}
            <div class="text-sm truncate">{picture}</div>
          {/each}
        </div>
      </div>
    {/if}
    
    <!-- Pin Configurations -->
    {#if ecu.pins && Object.keys(ecu.pins).length > 0}
      <div>
        <h5 class="text-lg font-semibold mb-4">Pin Configurations</h5>
        <div class="space-y-3">
          {#each Object.entries(ecu.pins) as [pin, config]}
            {@const pinConfig = config as { wire_color: string; ecu_function: string }}
            <div class="bg-dark-surface rounded-lg p-4">
              <div class="font-semibold text-lg mb-2">{pin}</div>
              <div class="space-y-2 text-sm">
                <div>
                  <span class="text-gray-400">Wire Color:</span>
                  <span class="ml-2">{pinConfig.wire_color || 'Not specified'}</span>
                </div>
                <div>
                  <span class="text-gray-400">ECU Function:</span>
                  <div class="ml-2 mt-1">{pinConfig.ecu_function || 'Not specified'}</div>
                </div>
              </div>
            </div>
          {/each}
        </div>
      </div>
    {:else}
      <div class="text-gray-400 text-center py-4">No pin configurations defined.</div>
    {/if}
  </div>
{/if}