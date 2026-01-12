import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/start_session': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/turn': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/voice_turn': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: '../app/static/dist',
    emptyOutDir: true,
  },
});
