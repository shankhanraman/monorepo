import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // "client" = the compose service name, so in-network browser checks can reach the dev server.
  server: { host: true, port: 5176, strictPort: true, allowedHosts: ['client'] },
});
