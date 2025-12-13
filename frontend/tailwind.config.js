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
        'pulse-ring': 'pulse-ring 0.75s ease-in-out 4',
      },
      keyframes: {
        'pulse-ring': {
          '0%, 100%': {
            boxShadow: '0 0 0 0 rgba(239, 68, 68, 0.7), 0 0 20px 5px rgba(239, 68, 68, 0.4)',
          },
          '50%': {
            boxShadow: '0 0 0 10px rgba(239, 68, 68, 0), 0 0 30px 15px rgba(239, 68, 68, 0.6)',
          },
        },
      },
    },
  },
  plugins: [],
}
