/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'Noto Sans SC', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        serif: ['Noto Serif SC', 'Source Han Serif', 'Songti SC', 'ui-serif', 'Georgia', 'serif'],
      },
      colors: {
        background: '#FDFBF7',
      },
      boxShadow: {
        'soft': '0 20px 40px -15px rgba(0, 0, 0, 0.05)',
      }
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
