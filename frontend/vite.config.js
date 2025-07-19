// frontend/vite.config.js
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        // --- THIS IS THE CHANGE ---
        target: 'http://localhost:8000', // Use localhost to avoid corporate proxy issues
        // --- END OF CHANGE ---
        changeOrigin: true,
        secure: false,
      },
    },
  },
});