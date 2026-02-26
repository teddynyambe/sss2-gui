<script lang="ts">
  import { deviceStore } from '$lib/stores/deviceStore.svelte';

  const canStatus = $derived(deviceStore.canStatus);

  // Show toast only when address cannot be claimed (contention error)
  const isVisible = $derived(canStatus.state === 'cannot_claim');
  const statusMessage = $derived(
    `SA 0x${canStatus.sa.toString(16).toUpperCase().padStart(2, '0')} is contested — another node has a lower NAME and won arbitration.`
  );
</script>

{#if isVisible}
  <div
    class="fixed bottom-4 right-4 bg-red-600 text-white px-6 py-4 rounded-lg shadow-lg z-50 min-w-[300px] max-w-md animate-slide-in-right"
    role="alert"
    aria-live="assertive"
  >
    <div class="flex items-start gap-3">
      <div class="flex-shrink-0">
        <svg
          class="w-6 h-6"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
      </div>
      <div class="flex-1">
        <h3 class="font-bold text-lg mb-1">Cannot Claim Address</h3>
        <p class="text-sm opacity-90">{statusMessage}</p>
        <p class="text-xs opacity-75 mt-1">
          Disconnect and reconnect to retry, or choose a different CAN interface.
        </p>
      </div>
    </div>
  </div>
{/if}

<style>
  @keyframes slide-in-right {
    from {
      transform: translateX(100%);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }

  .animate-slide-in-right {
    animation: slide-in-right 0.3s ease-out;
  }
</style>
