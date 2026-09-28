const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
    testDir: "./tests/e2e",
    use: {
        baseURL: "http://127.0.0.1:3000"
    },
    webServer: {
        command: "npm start",
        url: "http://127.0.0.1:3000",
        reuseExistingServer: !process.env.CI,
        timeout: 120000
    }
});
