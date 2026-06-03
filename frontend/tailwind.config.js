/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        charcoal: {
          DEFAULT: '#2D2D2D',
          light: '#3D3D3D',
          dark: '#1D1D1D',
        },
        gold: {
          DEFAULT: '#C9A84C',
          light: '#D4BA6A',
          dark: '#B08E30',
        },
        cream: '#FAFAF7',
        rule: '#E2DDD5',
        muted: '#6B6857',
        hint: '#9B9688',
      },
      fontFamily: {
        sans: ['Jost', 'Inter', 'system-ui', '-apple-system', 'sans-serif'],
        serif: ['Cormorant Garamond', 'Georgia', 'serif'],
      },
    },
  },
  plugins: [],
}
