// import { sveltekit } from '@sveltejs/kit/vite';
// import { defineConfig } from 'vite';
// import tailwindcss from '@tailwindcss/vite';

// export default defineConfig({
// 	plugins: [sveltekit(), tailwindcss()],
// 	server: {
// 		proxy: {
// 			'/api': {
// 				target: 'http://localhost:8000',
// 				changeOrigin: true,
// 				ws: true, // Enable WebSocket proxying
// 			}
// 		}
// 	}
// });
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import tailwindcss from '@tailwindcss/vite';

// If you run your backend on Kali (same VM), keep this as localhost.
// If your backend runs elsewhere, change it to that host (examples below).
const API_TARGET = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig({
	plugins: [sveltekit(), tailwindcss()],

	server: {
		host: '0.0.0.0', // <-- allows Mac to connect to the VM IP
		port: 5173,
		strictPort: true,

		// Optional but often needed on shared folders (Parallels / vm_shared)
		watch: {
			usePolling: true,
			interval: 300
		},

		proxy: {
			'/api': {
				target: API_TARGET,
				changeOrigin: true,
				ws: true

				// Optional: if backend expects /api, keep it.
				// If backend is mounted at / (no /api prefix), uncomment rewrite:
				// rewrite: (path) => path.replace(/^\/api/, ''),
			}
		}
	}
});
