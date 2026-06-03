/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#0B0B09',
          900: '#12120F',
          800: '#1C1C18',
          700: '#2A2A24',
          600: '#3A3A33',
          500: '#5B5B52',
          400: '#85857A',
          300: '#B0B0A4',
          200: '#D8D6CC',
        },
        bone: {
          DEFAULT: '#FAF8F2',
          50: '#FAF8F2',
          100: '#F4F0E8',
          200: '#ECE6D9',
          300: '#DFD7C5',
        },
        cream: '#F5EFE6',
        copper: {
          50: '#FBEBD8',
          100: '#F9D5AE',
          300: '#F6A85F',
          500: '#F08223',
          600: '#D46C13',
          700: '#A85200',
          DEFAULT: '#F7941D',
        },
        // Legacy aliases for existing components
        charcoal: {
          DEFAULT: '#1C1C18',
          light: '#2A2A24',
          dark: '#12120F',
        },
        gold: {
          DEFAULT: '#F7941D',
          light: '#F6A85F',
          dark: '#A85200',
        },
        rule: '#DFD7C5',
        muted: '#5B5B52',
        hint: '#85857A',
      },
      fontFamily: {
        sans: ['Montserrat', 'system-ui', '-apple-system', 'sans-serif'],
        serif: ['Fraunces', 'Georgia', 'serif'],
      },
    },
  },
  plugins: [],
}
