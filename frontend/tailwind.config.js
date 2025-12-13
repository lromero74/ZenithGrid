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
        'pulse-ring': 'pulse-ring 0.4s ease-in-out 8',
      },
      keyframes: {
        'pulse-ring': {
          '0%, 100%': {
            outline: '4px solid rgba(239, 68, 68, 1)',
            outlineOffset: '0px',
            filter: 'brightness(1)',
          },
          '50%': {
            outline: '8px solid rgba(239, 68, 68, 0.6)',
            outlineOffset: '4px',
            filter: 'brightness(1.1)',
          },
        },
      },
    },
  },
  plugins: [],
}
