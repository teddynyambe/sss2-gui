import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	// Consult https://svelte.dev/docs/kit/integrations
	// for more information about preprocessors
	preprocess: vitePreprocess(),

	kit: {
		// adapter-static: `npm run build` emits a pure client-side SPA into ./build
		// (index.html + _app/...). FastAPI (app-ui) serves these files at / on :8000,
		// so the UI and API share one origin — no node server, proxy, or CORS needed.
		// `fallback` makes every unknown path return index.html (client-side routing).
		// Requires ssr=false (set in src/routes/+layout.ts).
		adapter: adapter({ fallback: 'index.html' })
	}
};

export default config;
