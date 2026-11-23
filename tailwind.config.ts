import type { Config } from "tailwindcss";

// Design tokens — see docs/design-notes.md for rationale.
// Subject: internal trade software for builders' merchant staff, not a
// consumer product — palette and type are pulled from the trade-counter /
// spec-plate world (worksheet paper, steel chrome, safety-orange signal),
// deliberately not the cream-serif or dark-acid-green SaaS defaults.
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F0F0EA",
        ink: "#191B1D",
        "ink-muted": "#5B5F5A",
        steel: "#2B4A63",
        signal: "#D9491F",
        brass: "#B8933E",
        line: "#D3D0C6",
        success: "#3C7A4B",
      },
      fontFamily: {
        display: ["var(--font-archivo)", "sans-serif"],
        body: ["var(--font-inter)", "sans-serif"],
        mono: ["var(--font-plex-mono)", "monospace"],
      },
      borderRadius: {
        none: "0px",
        sm: "2px",
        DEFAULT: "2px",
      },
    },
  },
  plugins: [],
};

export default config;
