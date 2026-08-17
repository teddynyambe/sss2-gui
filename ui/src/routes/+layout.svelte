<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';
	import TouchKeyboard from '$lib/components/TouchKeyboard.svelte';

	let { children } = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

{@render children()}

<!-- On-screen keyboard for the touchscreen kiosk (auto-shows on text input focus) -->
<TouchKeyboard />
