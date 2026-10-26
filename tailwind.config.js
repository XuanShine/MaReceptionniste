/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/ma_receptionniste2/templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        paper: "rgb(244 243 239 / <alpha-value>)",
        ink: "rgb(28 27 25 / <alpha-value>)",
        line: "rgb(227 224 216 / <alpha-value>)",
        mute: "rgb(116 111 102 / <alpha-value>)",
        ready: "rgb(47 111 78 / <alpha-value>)",
        wait: "rgb(165 107 42 / <alpha-value>)",
        danger: "rgb(141 59 50 / <alpha-value>)",
      },
    },
  },
  plugins: [],
};
