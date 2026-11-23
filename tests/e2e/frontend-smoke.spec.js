const { test, expect } = require("@playwright/test");

// Stable, copy-independent selectors for the redesigned frontend.
test("home page exposes navigation", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("home-heading")).toBeVisible();
    await expect(page.getByTestId("nav-player-search")).toHaveAttribute("href", "/player-search.html");
    await page.getByTestId("nav-player-search").click();
    await expect(page.getByTestId("player-search-page")).toBeVisible();
});

test("front page loads and navigates to NBA Player Analytics", async ({ page, baseURL }) => {
    // Keep this page-load test local; no third-party services are needed.
    await page.route("**/*", route => {
        if (new URL(route.request().url()).origin !== new URL(baseURL).origin) {
            return route.abort();
        }
        return route.continue();
    });

    const homeResponse = await page.goto("/");
    expect(homeResponse.ok()).toBeTruthy();
    await expect(page.getByTestId("home-page")).toBeVisible();

    await page.getByTestId("nav-player-search").click();
    await expect(page).toHaveURL(/\/player-search\.html$/);
    await expect(page.getByTestId("player-search-page")).toBeVisible();
});

test("player analytics controls are present", async ({ page }) => {
    await page.goto("/player-search.html");
    await expect(page.getByTestId("player-search-heading")).toBeVisible();
    await expect(page.getByTestId("player-search-input")).toBeVisible();
    await expect(page.getByTestId("player-predictions").first()).toBeVisible();
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
