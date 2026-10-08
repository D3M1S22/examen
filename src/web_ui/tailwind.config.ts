import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#121316",
          dim: "#121316",
          bright: "#38393c",
          variant: "#343538",
          tint: "#c4c7ca",
        },
        "surface-container": {
          lowest: "#0d0e11",
          low: "#1b1b1f",
          DEFAULT: "#1f1f23",
          high: "#292a2d",
          highest: "#343538",
        },
        "on-surface": {
          DEFAULT: "#e3e2e6",
          variant: "#c4c7c9",
        },
        "inverse-surface": "#e3e2e6",
        "inverse-on-surface": "#303034",
        outline: {
          DEFAULT: "#8e9194",
          variant: "#44474a",
        },
        primary: {
          DEFAULT: "#ffffff",
          container: "#e0e3e6",
        },
        "on-primary": {
          DEFAULT: "#2d3133",
          container: "#626567",
        },
        "inverse-primary": "#5c5f61",
        secondary: {
          DEFAULT: "#c1c7d1",
          container: "#414750",
        },
        "on-secondary": {
          DEFAULT: "#2b3139",
          container: "#b0b5c0",
        },
        tertiary: {
          DEFAULT: "#ffffff",
          container: "#dee2ef",
        },
        "on-tertiary": {
          DEFAULT: "#2c313a",
          container: "#60646f",
        },
        error: {
          DEFAULT: "#ffb4ab",
          container: "#93000a",
        },
        "on-error": {
          DEFAULT: "#690005",
          container: "#ffdad6",
        },
        background: "#121316",
        "on-background": "#e3e2e6",
      },
      fontFamily: {
        sans: ['Geist', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      fontSize: {
        'display-lg': ['44px', { lineHeight: '52px', letterSpacing: '-0.03em', fontWeight: '500' }],
        'display-lg-mobile': ['32px', { lineHeight: '40px', letterSpacing: '-0.02em', fontWeight: '500' }],
        'headline-lg': ['28px', { lineHeight: '36px', letterSpacing: '-0.02em', fontWeight: '500' }],
        'headline-md': ['22px', { lineHeight: '30px', letterSpacing: '-0.015em', fontWeight: '500' }],
        'headline-sm': ['18px', { lineHeight: '26px', letterSpacing: '-0.01em', fontWeight: '500' }],
        'body-lg': ['16px', { lineHeight: '24px', letterSpacing: '-0.005em', fontWeight: '400' }],
        'body-md': ['14px', { lineHeight: '22px', letterSpacing: '0em', fontWeight: '400' }],
        'body-sm': ['12px', { lineHeight: '18px', letterSpacing: '0.01em', fontWeight: '400' }],
        'label-lg': ['13px', { lineHeight: '18px', letterSpacing: '0.02em', fontWeight: '500' }],
        'label-md': ['11px', { lineHeight: '16px', letterSpacing: '0.04em', fontWeight: '500' }],
        'label-sm': ['10px', { lineHeight: '14px', letterSpacing: '0.06em', fontWeight: '400' }],
      },
      borderRadius: {
        sm: "0.25rem",
        DEFAULT: "0.5rem",
        md: "0.75rem",
        lg: "1rem",
        xl: "1.5rem",
        full: "9999px",
      },
      spacing: {
        gutter: "1rem",
        "gutter-desktop": "1.5rem",
        margin: "1rem",
        "margin-touch": "1.5rem",
        "margin-desktop": "2.5rem",
        "space-xs": "0.25rem",
        "space-sm": "0.5rem",
        "space-md": "1rem",
        "space-lg": "1.5rem",
        "space-xl": "2rem",
        "space-2xl": "3rem",
      },
      minHeight: {
        touch: "48px",
      },
      minWidth: {
        touch: "48px",
      },
    },
  },
  plugins: [],
};
export default config;
