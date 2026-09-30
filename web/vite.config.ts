import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Relative asset paths: the same build works on localhost, Docker/nginx
  // and static hosts (GitHub Pages project sites) without a base-path rebuild.
  base: './',
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  preview: { port: 5173 },
});
