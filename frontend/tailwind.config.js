/** @type {import('tailwindcss').Config} */

/* Helper: create a Tailwind color that reads a CSS var as R G B channels */
const cv = (name) => `rgb(var(--color-${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        base: cv("base"),
        surface: cv("surface"),
        card: cv("card"),
        elevated: cv("elevated"),
        hover: cv("hover"),
        active: cv("active"),

        accent: {
          DEFAULT: cv("accent"),
          hover: cv("accent-hover"),
          soft: "rgb(var(--color-accent) / 0.12)",
          glow: "rgb(var(--color-accent) / 0.20)",
        },

        green: {
          DEFAULT: cv("green"),
          hover: cv("green-hover"),
        },

        danger: {
          DEFAULT: cv("danger"),
          hover: cv("danger-hover"),
        },

        warning: cv("warning"),

        border: {
          DEFAULT: cv("border"),
          subtle: cv("border-subtle"),
        },

        txt: {
          DEFAULT: cv("txt"),
          secondary: cv("txt-secondary"),
          muted: cv("txt-muted"),
          dim: cv("txt-dim"),
        },
      },

      fontFamily: {
        sans: ['"Segoe UI"', '"Inter"', '"SF Pro Display"', "system-ui", "sans-serif"],
      },

      borderRadius: {
        xl: "12px",
        "2xl": "16px",
      },

      boxShadow: {
        card: "var(--shadow-card)",
        glow: "var(--shadow-glow)",
        "glow-lg": "var(--shadow-glow-lg)",
      },
    },
  },
  plugins: [],
};
