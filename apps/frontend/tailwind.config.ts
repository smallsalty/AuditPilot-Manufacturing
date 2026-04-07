import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "../../packages/shared-types/src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#0f172a",
        slate: "#1e293b",
        haze: "#dbe4f0",
        steel: "#94a3b8",
        ember: "#d97706",
        signal: "#ef4444",
        mint: "#10b981",
      },
      boxShadow: {
        soft: "0 24px 60px rgba(15, 23, 42, 0.14)",
      },
    },
  },
  plugins: [],
};

export default config;
