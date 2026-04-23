/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        hebrew: ['Heebo', 'Arial', 'sans-serif'],
      },
      colors: {
        brand: {
          50:  '#f0f7ff',
          100: '#e0effe',
          200: '#bae0fd',
          300: '#7cc6fb',
          400: '#37a9f7',
          500: '#0d8de4',
          600: '#0270c2',
          700: '#025a9e',
          800: '#064d83',
          900: '#0b416d',
        },
      },
    },
  },
  plugins: [],
}
