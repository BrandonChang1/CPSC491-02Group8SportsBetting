require("dotenv").config();

const express = require("express");
const { execFile } = require("child_process");
const path = require("path");
const healthRouter = require("./backend/app/routes/health");
const playersRouter = require("./backend/app/routes/players");
const predictionsRouter = require("./backend/app/routes/predictions");
const { router: authRouter, requireAuth } = require("./backend/app/routes/auth");
const { notFoundHandler, errorHandler } = require("./backend/app/middleware/errorHandler");

const { fetchRecentTeamRecords, addPredictions } = require("./backend/app/services/teamWinPrediction");

const app = express();
const PORT = process.env.PORT || 3000;
const PYTHON_COMMAND =
    process.env.PYTHON_COMMAND ||
    (process.platform === "win32" ? "python" : "python3");

const FRONTEND_TEST_STARTING_BALANCE = 1000;
const frontendTestState = {
    balance: FRONTEND_TEST_STARTING_BALANCE,
    bets: [],
    mockGames: [],
    nextBetId: 1,
    nextMockGameId: 1
};

function parseMoneyAmount(value) {
    const amount = Number(value);
    if (amount === null) {
        return null;
    }

    const cents = Math.round(amount * 100);
    if (
        !Number.isSafeInteger(cents) ||
        cents <= 0 ||
        Math.abs(amount * 100 - cents) > 1e-7
    ) {
        return null;
    }

    return cents / 100;
}

function roundMoney(value) {
    return Math.round((value + Number.EPSILON) * 100) / 100;
}

app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));
app.use(authRouter);
app.use(healthRouter);
app.use(playersRouter);
app.use(predictionsRouter);

app.get("/app", requireAuth, (req, res) => {
    res.sendFile(path.join(__dirname, "protected", "home.html"));
});

function runPythonScript(scriptPath, args, res) {
    execFile(
        PYTHON_COMMAND,
        [scriptPath, ...args],
        (error, stdout, stderr) => {
            if (stdout && stdout.trim()) {
                try {
                    const result = JSON.parse(stdout);
                    return res.status(error ? 502 : 200).json(result);
                } catch (parseError) {
                    console.error(
                        "Could not parse Python output:",
                        parseError
                    );
                }
            }

            if (error) {
                console.error("Python error:", error);

                return res.status(500).json({
                    success: false,
                    message:
                        (stderr && stderr.trim()) ||
                        error.message,
                    data: []
                });
            }

            return res.status(500).json({
                success: false,
                message: "Python returned invalid JSON.",
                data: []
            });
        }
    );
}

function runPythonJson(scriptPath, args = []) {
    return new Promise((resolve, reject) => {
        execFile(
            PYTHON_COMMAND,
            [scriptPath, ...args],
            (error, stdout, stderr) => {
                if (!stdout || !stdout.trim()) {
                    return reject(
                        new Error(
                            (stderr && stderr.trim()) ||
                            (error && error.message) ||
                            "Python returned no output."
                        )
                    );
                }

                try {
                    const result = JSON.parse(stdout);
                    if (error && !result.success) {
                        return reject(
                            new Error(result.message || error.message)
                        );
                    }
                    return resolve(result);
                } catch (parseError) {
                    return reject(parseError);
                }
            }
        );
    });
}

function upcomingGamesScriptPath() {
    return path.join(__dirname, "scripts", "upcoming_games.py");
}

async function getRealUpcomingGames() {
    const result = await runPythonJson(upcomingGamesScriptPath());
    if (!result.success) {
        throw new Error(result.message || "Unable to retrieve NBA schedule.");
    }

    const now = Date.now();
    const sevenDaysFromNow = now + 7 * 24 * 60 * 60 * 1000;
    return (result.games || []).filter((game) => {
        const tipoff = Date.parse(game.tipoffUtc);
        return tipoff > now && tipoff <= sevenDaysFromNow;
    });
}

function settleMockGames() {
    const now = Date.now();

    for (const game of frontendTestState.mockGames) {
        if (game.status !== "final" && now >= Date.parse(game.endsAt)) {
            const sampleOneWins = Math.random() < 0.5;
            const winningScore = 105 + Math.floor(Math.random() * 21);
            const losingScore = 90 + Math.floor(Math.random() * 15);

            game.status = "final";
            game.winner = sampleOneWins ? "Sample Team 1" : "Sample Team 2";
            game.sampleTeam1Score = sampleOneWins ? winningScore : losingScore;
            game.sampleTeam2Score = sampleOneWins ? losingScore : winningScore;
        } else if (
            game.status === "scheduled" &&
            now >= Date.parse(game.startsAt)
        ) {
            game.status = "in_progress";
        }
    }
}

function settleBet(bet, winner) {
    if (bet.status !== "pending") {
        return;
    }

    bet.status = bet.selection === winner ? "won" : "lost";
    bet.winner = winner;
    bet.settledAt = new Date().toISOString();
    bet.payout = bet.status === "won" ? roundMoney(bet.amount * 2) : 0;

    if (bet.status === "won") {
        frontendTestState.balance = roundMoney(
            frontendTestState.balance + bet.payout
        );
    }
}

function settleMockBets() {
    const gamesById = new Map(
        frontendTestState.mockGames.map((game) => [game.id, game])
    );

    for (const bet of frontendTestState.bets) {
        if (bet.status !== "pending" || bet.gameType !== "mock") {
            continue;
        }

        const game = gamesById.get(bet.gameId);
        if (game && game.status === "final") {
            settleBet(bet, game.winner);
            bet.finalScore = `${game.awayTeam} ${game.sampleTeam1Score} - ${game.homeTeam} ${game.sampleTeam2Score}`;
        }
    }
}

async function settleRealBets() {
    const pendingGameIds = [
        ...new Set(
            frontendTestState.bets
                .filter(
                    (bet) =>
                        bet.status === "pending" && bet.gameType === "real"
                )
                .map((bet) => bet.gameId)
        )
    ];

    if (pendingGameIds.length === 0) {
        return;
    }

    const result = await runPythonJson(
        upcomingGamesScriptPath(),
        ["lookup", ...pendingGameIds]
    );

    const resultsById = new Map(
        (result.games || []).map((game) => [game.gameId, game])
    );

    for (const bet of frontendTestState.bets) {
        if (bet.status !== "pending" || bet.gameType !== "real") {
            continue;
        }

        const game = resultsById.get(bet.gameId);
        if (game && game.statusCode === 3 && game.winner) {
            settleBet(bet, game.winner);
            bet.finalScore = `${game.awayTeam.name} ${game.awayScore} - ${game.homeTeam.name} ${game.homeScore}`;
        }
    }
}

async function refreshFrontendTestState() {
    settleMockGames();
    settleMockBets();

    try {
        await settleRealBets();
    } catch (error) {
        console.error("Unable to settle real-game bets:", error.message);
    }
}

app.get("/run-test", (req, res) => {
    const team = req.query.team;

    if (!team) {
        return res.status(400).json({
            success: false,
            message: "No team was selected.",
            data: []
        });
    }

    const scriptPath = path.join(
        __dirname,
        "scripts",
        "webpage_team_search.py"
    );

    return runPythonScript(
        scriptPath,
        [team],
        res
    );
});

app.get("/search-players", (req, res) => {
    const query = req.query.q;

    if (!query || query.trim().length < 2) {
        return res.json({
            success: true,
            message: "Enter at least 2 characters.",
            data: []
        });
    }

    const scriptPath = path.join(
        __dirname,
        "scripts",
        "webpage_player_search.py"
    );

    return runPythonScript(
        scriptPath,
        ["search", query.trim()],
        res
    );
});

app.get("/player-stats", (req, res) => {
    const playerId = req.query.id;
    const review =
        (req.query.review || "5").toLowerCase();
    const validReviews =
        new Set(["5", "10", "season"]);

    if (!playerId) {
        return res.status(400).json({
            success: false,
            message: "No player ID was provided.",
            data: []
        });
    }

    if (!validReviews.has(review)) {
        return res.status(400).json({
            success: false,
            message:
                "Review must be 5, 10, or season.",
            data: []
        });
    }

    const scriptPath = path.join(
        __dirname,
        "scripts",
        "webpage_player_search.py"
    );

    return runPythonScript(
        scriptPath,
        [
            "stats",
            playerId,
            review
        ],
        res
    );
});

// Game-specific baseline probabilities, independent of simulated betting odds.
app.get("/api/upcoming-games/predictions", async (req, res) => {
    try {
        const games = await getRealUpcomingGames();
        const records = await fetchRecentTeamRecords();
        return res.json({ success: true, games: addPredictions(games, records) });
    } catch (error) {
        console.error("Unable to estimate upcoming games:", error);
        return res.status(503).json({ success: false, message: "Upcoming-game estimates are temporarily unavailable.", games: [] });
    }
});

app.get("/api/frontend-test-panel/state", async (req, res) => {
    await refreshFrontendTestState();

    try {
        const realGames = await getRealUpcomingGames();
        return res.json({
            success: true,
            balance: frontendTestState.balance,
            bets: frontendTestState.bets,
            mockGames: frontendTestState.mockGames,
            realGames
        });
    } catch (error) {
        return res.status(502).json({
            success: false,
            message: error.message,
            balance: frontendTestState.balance,
            bets: frontendTestState.bets,
            mockGames: frontendTestState.mockGames,
            realGames: []
        });
    }
});

app.post("/api/frontend-test-panel/deposit", (req, res) => {
    const amount = parseMoneyAmount(req.body.amount);
    if (amount === null) {
        return res.status(400).json({
            success: false,
            message: "Deposit amount must be a positive value with no more than two decimal places."
        });
    }

    frontendTestState.balance = roundMoney(frontendTestState.balance + amount);
    return res.json({ success: true, balance: frontendTestState.balance });
});

app.post("/api/frontend-test-panel/withdraw", (req, res) => {
    const amount = parseMoneyAmount(req.body.amount);
    if (amount === null) {
        return res.status(400).json({
            success: false,
            message: "Withdrawal amount must be a positive value with no more than two decimal places."
        });
    }
    if (amount > frontendTestState.balance) {
        return res.status(400).json({
            success: false,
            message: "Insufficient balance."
        });
    }

    frontendTestState.balance = roundMoney(frontendTestState.balance - amount);
    return res.json({ success: true, balance: frontendTestState.balance });
});

app.post("/api/frontend-test-panel/mock-games", (req, res) => {
    const createdAt = new Date();
    const startsAt = new Date(createdAt.getTime() + 20 * 1000);
    const endsAt = new Date(createdAt.getTime() + 40 * 1000);
    const game = {
        id: `mock-${frontendTestState.nextMockGameId++}`,
        gameType: "mock",
        awayTeam: "Sample Team 1",
        homeTeam: "Sample Team 2",
        createdAt: createdAt.toISOString(),
        startsAt: startsAt.toISOString(),
        endsAt: endsAt.toISOString(),
        status: "scheduled",
        winner: null,
        sampleTeam1Score: null,
        sampleTeam2Score: null
    };

    frontendTestState.mockGames.push(game);
    return res.status(201).json({ success: true, game });
});

app.post("/api/frontend-test-panel/bets", async (req, res) => {
    await refreshFrontendTestState();

    const amount = parseMoneyAmount(req.body.amount);
    const gameType = req.body.gameType;
    const gameId = String(req.body.gameId || "");
    const selection = String(req.body.selection || "");

    if (amount === null) {
        return res.status(400).json({
            success: false,
            message: "Bet amount must be a positive value with no more than two decimal places."
        });
    }
    if (amount > frontendTestState.balance) {
        return res.status(400).json({
            success: false,
            message: "Insufficient balance."
        });
    }

    let gameLabel;
    let validSelections;

    if (gameType === "mock") {
        const game = frontendTestState.mockGames.find(
            (item) => item.id === gameId
        );
        if (
            !game ||
            game.status !== "scheduled" ||
            Date.now() >= Date.parse(game.startsAt)
        ) {
            return res.status(400).json({
                success: false,
                message: "Betting is closed because that mock game has started."
            });
        }
        gameLabel = `${game.awayTeam} vs ${game.homeTeam}`;
        validSelections = [game.awayTeam, game.homeTeam];
    } else if (gameType === "real") {
        let realGames;
        try {
            realGames = await getRealUpcomingGames();
        } catch (error) {
            return res.status(502).json({
                success: false,
                message: error.message
            });
        }

        const game = realGames.find((item) => item.gameId === gameId);
        if (!game || Date.now() >= Date.parse(game.tipoffUtc)) {
            return res.status(400).json({
                success: false,
                message: "Betting is closed because that NBA game has started."
            });
        }
        gameLabel = `${game.awayTeam.name} vs ${game.homeTeam.name}`;
        validSelections = [game.awayTeam.name, game.homeTeam.name];
    } else {
        return res.status(400).json({
            success: false,
            message: "Invalid game type."
        });
    }

    if (!validSelections.includes(selection)) {
        return res.status(400).json({
            success: false,
            message: "Invalid team selection."
        });
    }

    frontendTestState.balance = roundMoney(frontendTestState.balance - amount);
    const bet = {
        id: frontendTestState.nextBetId++,
        gameType,
        gameId,
        gameLabel,
        selection,
        amount,
        odds: "1:1",
        status: "pending",
        payout: 0,
        placedAt: new Date().toISOString(),
        settledAt: null,
        finalScore: null,
        winner: null
    };
    frontendTestState.bets.unshift(bet);

    return res.status(201).json({
        success: true,
        balance: frontendTestState.balance,
        bet
    });
});

app.use(notFoundHandler);
app.use(errorHandler);

if (require.main === module) {
    app.listen(PORT, () => {
        console.log(
            `Server running at http://localhost:${PORT}`
        );
    });
}

module.exports = app;
