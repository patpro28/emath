/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./templates/**/*.html'],
  theme: {
    extend: {},
  },
  plugins: [
    require('@tailwindcss/typography'),
    require('@tailwindcss/line-clamp')
  ],
}
