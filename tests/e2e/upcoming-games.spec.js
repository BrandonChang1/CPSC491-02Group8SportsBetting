const { test, expect } = require("@playwright/test");

test("upcoming games page renders mocked games and refreshes", async ({ page }) => {
    let apiRequestCount = 0;

    const mockSchedule = {
        success: true,
        count: 2,
        games: [
            {
                gameId: "mock-game-1",
                tipoffUtc: "2026-10-01T02:00:00Z",
                status: "Scheduled",
                gameLabel: "Regular Season",
                awayTeam: {
                    name: "Los Angeles Lakers",
                    tricode: "LAL"
                },
                homeTeam: {
                    name: "Golden State Warriors",
                    tricode: "GSW"
                },
                arena: {
                    name: "Chase Center",
                    city: "San Francisco",
                    state: "CA"
                }
            },
            {
                gameId: "mock-game-2",
                tipoffUtc: "2026-10-02T23:30:00Z",
                status: "Scheduled",
                gameLabel: "Regular Season",
                awayTeam: {
                    name: "Boston Celtics",
                    tricode: "BOS"
                },
                homeTeam: {
                    name: "New York Knicks",
                    tricode: "NYK"
                },
                arena: {
                    name: "Madison Square Garden",
                    city: "New York",
                    state: "NY"
                }
            }
        ]
    };

    // Keep this frontend test independent of NBA/API server availability.
    await page.route("**/api/upcoming-games", async (route) => {
        apiRequestCount += 1;
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(mockSchedule)
        });
    });

    await page.goto("/upcoming-games.html");

    await expect(
        page.getByTestId("upcoming-games-heading")
    ).toBeVisible();
    await expect(page.getByTestId("schedule-status")).toHaveText("2 scheduled games found.");
    await expect(
        page.getByTestId("schedule-matchup").filter({ hasText: "Los Angeles Lakers at Golden State Warriors" })
    ).toBeVisible();
    await expect(
        page.getByTestId("schedule-matchup").filter({ hasText: "Boston Celtics at New York Knicks" })
    ).toBeVisible();
    await expect(page.getByText(/Chase Center/)).toBeVisible();
    await expect(page.getByText(/Madison Square Garden/)).toBeVisible();
    await expect.poll(() => apiRequestCount).toBe(1);

    await page.getByTestId("schedule-refresh").click();

    await expect.poll(() => apiRequestCount).toBe(2);
    await expect(page.getByTestId("schedule-status")).toHaveText("2 scheduled games found.");
});
