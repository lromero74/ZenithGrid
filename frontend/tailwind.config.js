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
        'pulse-ring': 'pulse-ring 0.5s ease-in-out 6',
      },
      keyframes: {
        'pulse-ring': {
          '0%, 100%': {
            boxShadow: '0 0 0 4px rgba(239, 68, 68, 0.8), 0 0 30px 10px rgba(239, 68, 68, 0.5)',
            transform: 'scale(1)',
          },
          '50%': {
            boxShadow: '0 0 0 12px rgba(239, 68, 68, 0.4), 0 0 50px 25px rgba(239, 68, 68, 0.3)',
            transform: 'scale(1.02)',
          },
        },
      },
    },
  },
  plugins: [],
}
