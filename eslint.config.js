module.exports = [
  {
    ignores: [
      "node_modules/**",
      ".venv/**",
      "build/**"
    ]
  },
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "commonjs",
      // Without these, eslint's no-undef rule flags every Node.js global
      // (process, console, require, __dirname, module) as undefined,
      // since this config's ecmaVersion/sourceType don't imply a Node
      // environment on their own.
      globals: {
        process: "readonly",
        console: "readonly",
        require: "readonly",
        module: "writable",
        exports: "writable",
        __dirname: "readonly",
        __filename: "readonly",
        Buffer: "readonly",
        global: "readonly"
      }
    },
    rules: {
      "no-undef": "error",
      "no-unreachable": "error",
      "no-unused-vars": "warn"
    }
  }
];