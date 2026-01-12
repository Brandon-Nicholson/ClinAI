/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        clinai: {
          bg: '#050505',
          'bg-secondary': '#0a0a0c',
          card: 'rgba(10, 10, 12, 0.96)',
          'card-solid': '#0a0a0c',
          border: '#1a1a20',
          'border-light': '#2a2a32',
          'border-glow': '#3b82f6',
          text: '#e5e7eb',
          'text-muted': '#9ca3af',
          'text-dim': '#6b7280',
          accent: '#3b82f6',
          'accent-hover': '#2563eb',
          'accent-cyan': '#06b6d4',
          'accent-purple': '#8b5cf6',
          success: '#22c55e',
          error: '#ef4444',
        },
      },
      animation: {
        'dot-bounce': 'dotBounce 1.4s ease-in-out infinite',
        'message-in': 'messageIn 0.22s ease-out forwards',
        'mic-pulse': 'micPulse 1.1s ease-out infinite',
        'dot-pulse': 'dotPulse 1.3s ease-in-out infinite',
        'fade-in': 'fadeIn 0.3s ease-out forwards',
      },
      keyframes: {
        dotBounce: {
          '0%, 80%, 100%': { transform: 'translateY(0)', opacity: '0.3' },
          '40%': { transform: 'translateY(-4px)', opacity: '1' },
        },
        messageIn: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        micPulse: {
          '0%': { transform: 'scale(1)', opacity: '0.8' },
          '100%': { transform: 'scale(1.5)', opacity: '0' },
        },
        dotPulse: {
          '0%, 100%': { opacity: '0.4' },
          '50%': { opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
      },
    },
  },
  plugins: [],
};
