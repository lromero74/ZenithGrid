/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '#3b82f6',
        secondary: '#8b5cf6',
        success: '#10b981',
        danger: '#ef4444',
        warning: '#f59e0b',
      },
      animation: {
        'pulse-ring': 'pulse-ring 0.5s ease-in-out 5',
        'pulse-glow': 'pulse-glow 1s ease-in-out infinite',
      },
      keyframes: {
        'pulse-ring': {
          '0%, 100%': {
            outline: '3px solid rgba(239, 68, 68, 0.8)',
            outlineOffset: '0px',
          },
          '50%': {
            outline: '3px solid rgba(239, 68, 68, 0.4)',
            outlineOffset: '5px',
          },
        },
        'pulse-glow': {
          '0%, 100%': {
            boxShadow: '0 0 8px 2px currentColor',
            opacity: '1',
          },
          '50%': {
            boxShadow: '0 0 20px 6px currentColor',
            opacity: '0.8',
          },
        },
      },
    },
  },
  plugins: [],
}
