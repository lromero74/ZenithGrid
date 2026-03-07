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
        'theme-primary': 'var(--color-primary)',
        'theme-base': 'var(--color-bg-base)',
        'theme-card': 'var(--color-bg-card)',
        'theme-header': 'var(--color-bg-header)',
        'theme-border': 'var(--color-border)',
        'theme-border-light': 'var(--color-border-light)',
      },
      boxShadow: {
        'neon': 'var(--neon-shadow)',
        'neon-sm': 'var(--neon-shadow-sm)',
      },
      animation: {
        'pulse-ring': 'pulse-ring 0.5s ease-in-out 5',
        'fade-in': 'fade-in 600ms ease-out',
        'scale-in': 'scale-in 400ms ease-out 200ms both',
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
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(0.9)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
      },
    },
  },
  plugins: [],
}
