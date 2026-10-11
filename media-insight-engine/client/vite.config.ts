import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The config runs in Node; declared here instead of adding @types/node for one variable.
declare const process: { env: Record<string, string | undefined> };

export default defineConfig({
  plugins: [react()],
  // "client" = the compose service name, so in-network browser checks can reach the dev server.
  // VITE_USE_POLLING (set in docker-compose): Windows bind mounts don't deliver file-change events into Docker,
  // so without polling the container keeps serving stale code after edits.
  server: {
    host: true,
    port: 5176,
    strictPort: true,
    allowedHosts: ['client'],
    watch: process.env.VITE_USE_POLLING ? { usePolling: true, interval: 500 } : undefined,
  },
});
