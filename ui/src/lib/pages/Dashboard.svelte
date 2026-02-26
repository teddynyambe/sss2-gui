<script lang="ts">
  import { deviceStore } from '$lib/stores/deviceStore.svelte';
  import DashboardCard from '$lib/components/DashboardCard.svelte';
  import SPNMonitorPanel from '$lib/components/SPNMonitorPanel.svelte';
  import PinnedPotsPanel from '$lib/components/PinnedPotsPanel.svelte';

  const monitoredSA = $derived(deviceStore.monitoredECUSA);
  const potCount = $derived(deviceStore.catalog?.potentiometers?.length ?? 0);
  const hasPinnedPots = $derived(Object.keys(deviceStore.pinnedPotIds).length > 0);
</script>

<div class="max-w-7xl mx-auto">
  {#if hasPinnedPots || monitoredSA !== null}
    <!-- Split layout: pinned pots on left, content on right -->
    <div class="flex gap-3 items-start">
      <PinnedPotsPanel />
      <div class="flex-1 min-w-0">
        {#if monitoredSA !== null}
          <SPNMonitorPanel />
        {:else}
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <DashboardCard title="Potentiometers" count={potCount} />
            <DashboardCard title="VOUTs" count={0} comingSoon={true} />
            <DashboardCard title="PWMs" count={0} comingSoon={true} />
            <DashboardCard title="CAN" count={0} comingSoon={true} />
            <DashboardCard title="J1708" count={0} comingSoon={true} />
          </div>
        {/if}
      </div>
    </div>
  {:else}
    <!-- Default: summary cards only -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <DashboardCard title="Potentiometers" count={potCount} />
      <DashboardCard title="VOUTs" count={0} comingSoon={true} />
      <DashboardCard title="PWMs" count={0} comingSoon={true} />
      <DashboardCard title="CAN" count={0} comingSoon={true} />
      <DashboardCard title="J1708" count={0} comingSoon={true} />
    </div>
  {/if}
</div>
