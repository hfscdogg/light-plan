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
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
