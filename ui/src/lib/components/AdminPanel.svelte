<script lang="ts">
  import { apiClient } from '$lib/api/client';

  let { open = $bindable(false) }: { open?: boolean } = $props();

  type Action =
    | 'exit-console'
    | 'exit-desktop'
    | 'restart-gui'
    | 'restart-app'
    | 'reboot'
    | 'shutdown'
    | 'update';

  const ACTIONS: { id: Action; label: string; desc: string; danger?: boolean }[] = [
    { id: 'exit-desktop', label: 'Exit to Desktop', desc: 'Stop the kiosk and start the Pi desktop' },
    { id: 'exit-console', label: 'Exit to Console', desc: 'Stop the kiosk and open a login console' },
    { id: 'update', label: 'Update & Restart', desc: 'Pull latest, rebuild UI, restart' },
    { id: 'restart-gui', label: 'Restart GUI', desc: 'Relaunch the kiosk browser' },
    { id: 'restart-app', label: 'Restart App', desc: 'Restart backend + kiosk' },
    { id: 'reboot', label: 'Reboot', desc: 'Restart the whole device', danger: true },
    { id: 'shutdown', label: 'Shut Down', desc: 'Power off the device', danger: true },
  ];

  // Actions that kill the kiosk browser → the response may never arrive; that's fine.
  const GUI_KILLING: Action[] = ['exit-console', 'exit-desktop', 'restart-gui', 'restart-app', 'reboot', 'shutdown'];

  let step = $state<'pin' | 'actions'>('pin');
  let pin = $state('');
  let pending = $state<Action | null>(null);
  let busy = $state(false);
  let error = $state<string | null>(null);
  let notice = $state<string | null>(null);

  function reset() {
    step = 'pin';
    pin = '';
    pending = null;
    busy = false;
    error = null;
    notice = null;
  }

  function close() {
    open = false;
    reset();
  }

  function press(d: string) {
    if (pin.length < 12) pin += d;
  }
  function backspace() {
    pin = pin.slice(0, -1);
  }

  function unlock() {
    if (!pin) {
      error = 'Enter the admin PIN';
      return;
    }
    error = null;
    step = 'actions';
  }

  async function run(a: Action) {
    busy = true;
    error = null;
    notice = null;
    try {
      await apiClient.systemAction(a, pin);
      notice = GUI_KILLING.includes(a) ? 'Command sent — the screen will change shortly…' : 'Done.';
      pending = null;
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Action failed';
      // A dropped connection is expected for actions that kill the browser.
      if (GUI_KILLING.includes(a) && /failed to fetch|networkerror|load failed/i.test(msg)) {
        notice = 'Command sent — the screen will change shortly…';
      } else {
        error = msg.includes('Invalid PIN') ? 'Invalid PIN' : msg;
        if (error === 'Invalid PIN') step = 'pin';
      }
      pending = null;
    } finally {
      busy = false;
    }
  }

  // Keyboard: Escape closes; digits feed the PIN pad.
  function onKey(e: KeyboardEvent) {
    if (!open) return;
    if (e.key === 'Escape') close();
    else if (step === 'pin' && /^[0-9]$/.test(e.key)) press(e.key);
    else if (step === 'pin' && e.key === 'Backspace') backspace();
    else if (step === 'pin' && e.key === 'Enter') unlock();
  }
</script>

<svelte:window onkeydown={onKey} />

{#if open}
  <!-- Overlay -->
  <div
    class="fixed inset-0 z-[200] bg-black/70 flex items-center justify-center p-4"
    role="dialog"
    aria-modal="true"
    aria-label="Admin panel"
  >
    <div class="w-full max-w-md bg-dark-card rounded-xl shadow-2xl border border-gray-700 overflow-hidden">
      <div class="flex items-center justify-between px-4 py-3 border-b border-gray-700 bg-[#0a2338]">
        <h2 class="text-base font-semibold">Maintenance / Admin</h2>
        <button class="text-gray-400 hover:text-white text-xl leading-none min-h-touch px-2" onclick={close}>✕</button>
      </div>

      {#if step === 'pin'}
        <div class="p-5">
          <p class="text-sm text-gray-400 mb-3">Enter admin PIN</p>
          <div
            class="h-12 rounded bg-dark-bg border border-gray-600 flex items-center justify-center tracking-[0.4em] text-2xl font-mono mb-4"
          >
            {'•'.repeat(pin.length) || ' '}
          </div>
          <div class="grid grid-cols-3 gap-2">
            {#each ['1', '2', '3', '4', '5', '6', '7', '8', '9'] as d (d)}
              <button
                class="py-4 rounded bg-dark-bg hover:bg-dark-accent text-xl font-medium min-h-touch"
                onclick={() => press(d)}>{d}</button
              >
            {/each}
            <button class="py-4 rounded bg-dark-bg hover:bg-dark-accent text-sm min-h-touch" onclick={backspace}>⌫</button>
            <button class="py-4 rounded bg-dark-bg hover:bg-dark-accent text-xl font-medium min-h-touch" onclick={() => press('0')}>0</button>
            <button class="py-4 rounded bg-green-700 hover:bg-green-600 text-sm font-semibold min-h-touch" onclick={unlock}>Unlock</button>
          </div>
          {#if error}<p class="text-sm text-red-400 mt-3">{error}</p>{/if}
        </div>
      {:else}
        <div class="p-4">
          {#if notice}
            <p class="text-sm text-green-400 mb-3">{notice}</p>
          {/if}
          {#if error}
            <p class="text-sm text-red-400 mb-3">{error}</p>
          {/if}

          <div class="grid gap-2">
            {#each ACTIONS as a (a.id)}
              {#if pending === a.id}
                <div class="rounded border border-yellow-600/60 bg-yellow-900/20 p-3">
                  <p class="text-sm mb-2">Confirm <span class="font-semibold">{a.label}</span>?</p>
                  <div class="flex gap-2">
                    <button
                      class="flex-1 py-2 rounded bg-gray-700 hover:bg-gray-600 text-sm min-h-touch"
                      onclick={() => (pending = null)}
                      disabled={busy}>Cancel</button
                    >
                    <button
                      class="flex-1 py-2 rounded text-sm font-semibold min-h-touch disabled:opacity-50 {a.danger
                        ? 'bg-red-700 hover:bg-red-600'
                        : 'bg-green-700 hover:bg-green-600'}"
                      onclick={() => run(a.id)}
                      disabled={busy}>{busy ? '…' : 'Confirm'}</button
                    >
                  </div>
                </div>
              {:else}
                <button
                  class="flex items-center justify-between text-left rounded border px-3 py-3 min-h-touch transition-colors
                    {a.danger
                    ? 'border-red-800/60 hover:bg-red-900/20'
                    : 'border-gray-700 hover:bg-dark-accent'}"
                  onclick={() => { pending = a.id; notice = null; error = null; }}
                  disabled={busy}
                >
                  <span>
                    <span class="block text-sm font-medium {a.danger ? 'text-red-300' : ''}">{a.label}</span>
                    <span class="block text-xs text-gray-400">{a.desc}</span>
                  </span>
                  <span class="text-gray-500">›</span>
                </button>
              {/if}
            {/each}
          </div>

          <p class="text-[11px] text-gray-500 mt-4">
            Keyboard escape hatch: <span class="font-mono">Ctrl+Alt+F2</span> for a login console, or SSH in and run
            <span class="font-mono">sudo systemctl stop sss2-kiosk</span>.
          </p>
        </div>
      {/if}
    </div>
  </div>
{/if}
