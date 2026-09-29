module.exports = [
  {
    ignores: [
      "node_modules/**",
      "build/**"
    ]
  },
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "commonjs"
    },
    rules: {
      "no-undef": "error",
      "no-unreachable": "error",
      "no-unused-vars": "warn"
    }
  }
];