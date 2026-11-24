/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#080b10", 900: "#0b0f14", 850: "#0f151c", 800: "#121a23", 700: "#1a2430", 600: "#243140", 500: "#33445a" },
        sev: { critical: "#f43f5e", error: "#fb923c", warning: "#fbbf24", info: "#38bdf8", debug: "#64748b" },
        accent: { DEFAULT: "#22d3ee", dim: "#0e7490" },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
