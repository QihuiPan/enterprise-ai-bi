import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: "charts", test: /node_modules[\\/](recharts|d3-|victory-vendor)/ },
            { name: "react", test: /node_modules[\\/](react|react-dom|scheduler)/ },
          ],
        },
      },
    },
  },
});
