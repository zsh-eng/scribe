/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}"],
  theme: {
    borderRadius: {
        none: "0",
        sm: "0",
        DEFAULT: "0",
        md: "0",
        lg: "0",
        xl: "0",
        "2xl": "0",
        "3xl": "0",
        full: "9999px",
      },
    extend: {
      colors: {
        // Hansard Editorial palette
        "page-bg": "#f5f1eb",
        surface: "#fdfcf9",
        warm: "#faf7f3",
        ink: "#1a1612",
        "ink-soft": "#5a5248",
        "ink-muted": "#8a8078",
        accent: "#8b2500",
        "accent-light": "#a63a14",
        border: "#e8e0d4",
        "border-light": "#f0ece5",
        // Party colors
        "wp-blue": "#2a5fa0",
        "wp-blue-bg": "#e8f0fa",
        "pap-red": "#8b2500",
        "pap-red-bg": "#faeee8",
        // Status colors
        "status-passed": "#2d6a3f",
        "status-passed-bg": "#e6f2eb",
        "status-reading": "#6b5b2e",
        "status-reading-bg": "#f5f0e0",
      },
      fontFamily: {
        display: ["Newsreader", "Georgia", "serif"],
        masthead: ["Playfair Display", "Georgia", "serif"],
        body: ["Source Serif 4", "Georgia", "serif"],
        sans: ["DM Sans", "system-ui", "sans-serif"],
      },
      fontSize: {
        // Custom type scale with optical sizing
        "display-xl": [
          "clamp(2.6rem, 5.5vw, 4.2rem)",
          { lineHeight: "1.12", fontWeight: "300" },
        ],
        "display-lg": [
          "clamp(1.8rem, 3.5vw, 2.6rem)",
          { lineHeight: "1.2", fontWeight: "400" },
        ],
        "display-md": [
          "clamp(1.4rem, 2.5vw, 1.8rem)",
          { lineHeight: "1.25", fontWeight: "400" },
        ],
        label: [
          "0.65rem",
          { lineHeight: "1", letterSpacing: "0.25em", fontWeight: "600" },
        ],
        "label-sm": [
          "0.6rem",
          { lineHeight: "1", letterSpacing: "0.15em", fontWeight: "600" },
        ],
      },
      letterSpacing: {
        widest: "0.25em",
        wider: "0.12em",
        wide: "0.08em",
      },
      animation: {
        "fade-up": "fadeUp 0.4s ease-out both",
        "fade-in": "fadeIn 0.35s ease-out both",
        "slide-down": "slideDown 0.35s ease-out both",
      },
      keyframes: {
        fadeUp: {
          from: { opacity: "0", transform: "translateY(16px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        fadeIn: {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        slideDown: {
          from: { opacity: "0", transform: "translateY(-8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      maxWidth: {
        content: "960px",
        prose: "720px",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
