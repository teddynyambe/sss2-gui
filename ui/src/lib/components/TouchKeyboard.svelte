<script lang="ts">
  // Self-contained on-screen keyboard for the touchscreen kiosk (no physical
  // keyboard for data entry). Shows automatically when any text input/textarea
  // gains focus; feeds keystrokes back via native input events so Svelte bindings
  // update. Svelte 5 runes: reactive state MUST be $state (a plain `let` won't
  // re-render). `active` is a DOM node, kept as a plain let (never $state — Svelte
  // would try to deep-proxy the element).
  import { onMount } from 'svelte';

  let visible = $state(false);
  let uppercase = $state(false);
  let numeric = $state(false);
  let active: HTMLInputElement | HTMLTextAreaElement | null = null;

  const TEXT_TYPES = ['text', 'password', 'email', 'search', 'url', 'tel', 'number'];

  const letters = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
    ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
    ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
    ['Shift', 'z', 'x', 'c', 'v', 'b', 'n', 'm', '⌫'],
    ['Close', 'Space', 'Enter'],
  ];
  const numbers = [
    ['1', '2', '3'],
    ['4', '5', '6'],
    ['7', '8', '9'],
    ['.', '0', '-'],
    ['Close', '⌫', 'Enter'],
  ];

  onMount(() => {
    const onFocusIn = (e: FocusEvent) => {
      const el = e.target;
      const isText =
        el instanceof HTMLTextAreaElement ||
        (el instanceof HTMLInputElement && TEXT_TYPES.includes(el.type));
      if (!isText) return;
      if (el.readOnly || el.disabled) return;

      active = el;
      numeric =
        el instanceof HTMLInputElement &&
        (el.type === 'number' ||
          el.type === 'tel' ||
          el.inputMode === 'numeric' ||
          el.inputMode === 'decimal');
      visible = true;
      // Make sure the focused field isn't hidden behind the keyboard.
      setTimeout(() => el.scrollIntoView({ block: 'center', behavior: 'smooth' }), 50);
    };

    const onFocusOut = () => {
      // Delay so tapping keys (which keep focus) or moving between fields doesn't flicker.
      setTimeout(() => {
        const el = document.activeElement;
        const stillInput =
          el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement;
        if (!stillInput) visible = false;
      }, 150);
    };

    document.addEventListener('focusin', onFocusIn);
    document.addEventListener('focusout', onFocusOut);
    return () => {
      document.removeEventListener('focusin', onFocusIn);
      document.removeEventListener('focusout', onFocusOut);
    };
  });

  function insert(text: string) {
    if (!active) return;
    const start = active.selectionStart ?? active.value.length;
    const end = active.selectionEnd ?? active.value.length;
    try {
      active.setRangeText(text, start, end, 'end');
    } catch {
      active.value += text; // number inputs don't support setRangeText
    }
    active.dispatchEvent(new Event('input', { bubbles: true }));
    active.focus({ preventScroll: true });
  }

  function backspace() {
    if (!active) return;
    const start = active.selectionStart ?? active.value.length;
    const end = active.selectionEnd ?? active.value.length;
    try {
      if (start !== end) active.setRangeText('', start, end, 'end');
      else if (start > 0) active.setRangeText('', start - 1, start, 'end');
    } catch {
      active.value = active.value.slice(0, -1);
    }
    active.dispatchEvent(new Event('input', { bubbles: true }));
    active.focus({ preventScroll: true });
  }

  function press(key: string) {
    if (!active) return;
    switch (key) {
      case 'Close':
        visible = false;
        active.blur();
        return;
      case 'Shift':
        uppercase = !uppercase;
        return;
      case 'Space':
        insert(' ');
        return;
      case '⌫':
        backspace();
        return;
      case 'Enter':
        if (active instanceof HTMLTextAreaElement) {
          insert('\n');
        } else {
          active.dispatchEvent(
            new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }),
          );
          visible = false;
          active.blur();
        }
        return;
      default:
        insert(uppercase ? key.toUpperCase() : key);
        if (uppercase) uppercase = false;
    }
  }
</script>

{#if visible}
  <div class="kb">
    {#each numeric ? numbers : letters as row, i (i)}
      <div class="row">
        {#each row as key (key)}
          <button
            type="button"
            class:wide={key === 'Space'}
            class:special={['Shift', 'Close', 'Enter', 'Space', '⌫'].includes(key)}
            onpointerdown={(e) => {
              e.preventDefault();
              press(key);
            }}
          >
            {uppercase && key.length === 1 ? key.toUpperCase() : key}
          </button>
        {/each}
      </div>
    {/each}
  </div>
{/if}

<style>
  .kb {
    position: fixed;
    right: 0;
    bottom: 0;
    left: 0;
    z-index: 2147483647;
    padding: 8px;
    background: #18181b;
    border-top: 2px solid #3f3f46;
    box-shadow: 0 -4px 18px #0008;
    touch-action: none;
  }
  .row {
    display: flex;
    justify-content: center;
    gap: 6px;
    margin: 5px 0;
  }
  button {
    min-width: 7%;
    height: 52px;
    padding: 0 12px;
    border: 1px solid #71717a;
    border-radius: 6px;
    background: #3f3f46;
    color: white;
    font-size: 20px;
    font-weight: 600;
  }
  button:active {
    background: #2563eb;
  }
  button.special {
    background: #27272a;
    font-size: 16px;
  }
  button.wide {
    flex: 0 1 42%;
  }
</style>
