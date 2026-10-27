const { test, expect } = require("@playwright/test");

// Stable, copy-independent selectors for the redesigned frontend.
test("home page exposes navigation", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("home-heading")).toBeVisible();
    await expect(page.getByTestId("nav-player-search")).toHaveAttribute("href", "/player-search.html");
    await page.getByTestId("nav-player-search").click();
    await expect(page.getByTestId("player-search-page")).toBeVisible();
});

test("player analytics controls are present", async ({ page }) => {
    await page.goto("/player-search.html");
    await expect(page.getByTestId("player-search-heading")).toBeVisible();
    await expect(page.getByTestId("player-search-input")).toBeVisible();
    await page.getByTestId("review-last-10").check();
    await expect(page.getByTestId("review-last-10")).toBeChecked();
});

test("team statistics selection is available", async ({ page }) => {
    await page.goto("/test.html");
    await expect(page.getByTestId("team-stats-heading")).toBeVisible();
    await page.getByTestId("team-select").selectOption("Boston Celtics");
    await expect(page.getByTestId("team-select")).toHaveValue("Boston Celtics");
    await expect(page.getByTestId("team-submit")).toBeVisible();
});

test("login and registration forms render", async ({ page }) => {
    await page.goto("/login.html");
    await expect(page.getByTestId("login-heading")).toBeVisible();
    await expect(page.getByTestId("login-identifier")).toBeVisible();
    await expect(page.getByTestId("login-submit")).toBeVisible();
    await page.goto("/create-account.html");
    await expect(page.getByTestId("create-account-heading")).toBeVisible();
    await expect(page.getByTestId("register-email")).toBeVisible();
    await expect(page.getByTestId("register-submit")).toBeVisible();
});

test("test panel opens from home page", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("nav-frontend-test-panel").click();
    await expect(page.getByRole("heading", { name: "User Flow Test Panel" })).toBeVisible();
});
