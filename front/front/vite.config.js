import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Vite configuration.
// - The React plugin enables JSX + Fast Refresh.
// - Images imported from `src/assets/` are hashed and bundled automatically,
//   so you only need to drop PNGs into that folder and keep the file names.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: false,
  },
});

