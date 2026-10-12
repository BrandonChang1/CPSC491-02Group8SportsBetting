require("dotenv").config();

const express = require("express");
const { execFile } = require("child_process");
const path = require("path");
const healthRouter = require("./backend/app/routes/health");
const playersRouter = require("./backend/app/routes/players");
const { router: authRouter, requireAuth } = require("./backend/app/routes/auth");
const { notFoundHandler, errorHandler } = require("./backend/app/middleware/errorHandler");

const app = express();
const PORT = process.env.PORT || 3000;
const PYTHON_COMMAND =
    process.env.PYTHON_COMMAND ||
    (process.platform === "win32" ? "python" : "python3");

const frontendTestState = {
    balance: 1000,
    bets: [],
    mockGames: [],
    nextBetId: 1,
    nextMockGameId: 1,
};

function money(value) {
    return Math.round((Number(value) + Number.EPSILON) * 100) / 100;
}

function settleBet(bet, winner) {
    if (bet.status !== "pending") {
        return;
    }

    bet.settledAt = new Date().toISOString();
    if (bet.selection === winner) {
        bet.status = "won";
        bet.payout = money(bet.amount * 2);
        frontendTestState.balance = money(frontendTestState.balance + bet.payout);
    } else {
        bet.status = "lost";
        bet.payout = 0;
    }
}

function settleMockGames() {
    const now = Date.now();

    for (const game of frontendTestState.mockGames) {
        if (game.status === "final" || now < Date.parse(game.endsAt)) {
            continue;
        }

        game.status = "final";
        game.winner = game.hiddenWinner;

        for (const bet of frontendTestState.bets) {
            if (bet.gameType === "mock" && bet.gameId === game.id) {
                settleBet(bet, game.winner);
            }
        }
    }
}

function runPythonJson(scriptPath, args = []) {
    return new Promise((resolve, reject) => {
        execFile(PYTHON_COMMAND, [scriptPath, ...args], (error, stdout, stderr) => {
            if (!stdout || !stdout.trim()) {
                reject(new Error((stderr && stderr.trim()) || (error && error.message) || "Python returned no JSON."));
                return;
            }

            try {
                resolve(JSON.parse(stdout));
            } catch (parseError) {
                reject(parseError);
            }
        });
    });
}

async function settleRealBets() {
    const now = Date.now();
    const pending = frontendTestState.bets.filter((bet) => {
        if (bet.gameType !== "real" || bet.status !== "pending") {
            return false;
        }

        if (Date.parse(bet.tipoffUtc) > now) {
            return false;
        }

        return !bet.lastCheckedAt || now - Date.parse(bet.lastCheckedAt) >= 60000;
    });

    if (pending.length === 0) {
        return;
    }

    const checkedAt = new Date().toISOString();
    for (const bet of pending) {
        bet.lastCheckedAt = checkedAt;
    }

    const gameIds = [...new Set(pending.map((bet) => bet.gameId))];
    const scriptPath = path.join(__dirname, "scripts", "upcoming_games.py");
    const result = await runPythonJson(scriptPath, ["status", ...gameIds]);

    if (!result.success) {
        throw new Error(result.message || "Unable to check NBA game results.");
    }

    const byId = new Map((result.games || []).map((game) => [String(game.gameId), game]));
    for (const bet of pending) {
        const game = byId.get(String(bet.gameId));
        if (!game || game.statusCode !== 3 || !game.winner) {
            continue;
        }

        bet.finalScore = `${game.awayScore}-${game.homeScore}`;
        settleBet(bet, game.winner);
    }
}

app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));
app.use(authRouter);
app.use(healthRouter);
app.use(playersRouter);

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

app.get("/api/upcoming-games", (req, res) => {
    const scriptPath = path.join(
        __dirname,
        "scripts",
        "upcoming_games.py"
    );

    return runPythonScript(
        scriptPath,
        [],
        res
    );
});

app.get("/api/frontend-test/state", async (req, res) => {
    settleMockGames();

    let settlementWarning = null;
    try {
        await settleRealBets();
    } catch (error) {
        settlementWarning = error.message;
    }

    const mockGames = frontendTestState.mockGames.map(({ hiddenWinner, ...game }) => game);
    const bets = frontendTestState.bets.map(({ lastCheckedAt, ...bet }) => bet);

    return res.json({
        success: true,
        balance: frontendTestState.balance,
        bets,
        mockGames,
        settlementWarning,
    });
});

app.post("/api/frontend-test/deposit", (req, res) => {
    const amount = money(req.body.amount);
    if (!Number.isFinite(amount) || amount <= 0) {
        return res.status(400).json({ success: false, message: "Deposit amount must be greater than zero." });
    }

    frontendTestState.balance = money(frontendTestState.balance + amount);
    return res.json({ success: true, balance: frontendTestState.balance });
});

app.post("/api/frontend-test/withdraw", (req, res) => {
    const amount = money(req.body.amount);
    if (!Number.isFinite(amount) || amount <= 0) {
        return res.status(400).json({ success: false, message: "Withdrawal amount must be greater than zero." });
    }

    if (amount > frontendTestState.balance) {
        return res.status(400).json({ success: false, message: "Withdrawal exceeds the current balance." });
    }

    frontendTestState.balance = money(frontendTestState.balance - amount);
    return res.json({ success: true, balance: frontendTestState.balance });
});

app.post("/api/frontend-test/mock-games", (req, res) => {
    settleMockGames();

    const createdAt = new Date();
    const startsAt = new Date(createdAt.getTime() + 2 * 60 * 1000);
    const endsAt = new Date(createdAt.getTime() + 3 * 60 * 1000);
    const winner = Math.random() < 0.5 ? "sample-team-1" : "sample-team-2";

    const game = {
        id: `mock-${frontendTestState.nextMockGameId++}`,
        homeTeam: "Sample Team 1",
        awayTeam: "Sample Team 2",
        createdAt: createdAt.toISOString(),
        startsAt: startsAt.toISOString(),
        endsAt: endsAt.toISOString(),
        status: "scheduled",
        winner: null,
        hiddenWinner: winner,
    };

    frontendTestState.mockGames.unshift(game);
    const { hiddenWinner, ...publicGame } = game;
    return res.status(201).json({ success: true, game: publicGame });
});

app.post("/api/frontend-test/bets", (req, res) => {
    settleMockGames();

    const amount = money(req.body.amount);
    const gameType = req.body.gameType === "mock" ? "mock" : "real";
    const selection = String(req.body.selection || "");

    if (!Number.isFinite(amount) || amount <= 0) {
        return res.status(400).json({ success: false, message: "Bet amount must be greater than zero." });
    }

    if (amount > frontendTestState.balance) {
        return res.status(400).json({ success: false, message: "Bet amount exceeds the current balance." });
    }

    let bet;
    if (gameType === "mock") {
        const game = frontendTestState.mockGames.find((item) => item.id === req.body.gameId);
        if (!game) {
            return res.status(404).json({ success: false, message: "Mock game not found." });
        }
        if (Date.now() >= Date.parse(game.startsAt)) {
            return res.status(400).json({ success: false, message: "Betting is closed because the mock game has started." });
        }
        if (!new Set(["sample-team-1", "sample-team-2"]).has(selection)) {
            return res.status(400).json({ success: false, message: "Choose one of the mock teams." });
        }

        bet = {
            id: frontendTestState.nextBetId++,
            gameType: "mock",
            gameId: game.id,
            gameLabel: `${game.awayTeam} @ ${game.homeTeam}`,
            tipoffUtc: game.startsAt,
            selection,
            selectionLabel: selection === "sample-team-1" ? game.homeTeam : game.awayTeam,
            amount,
            odds: "1:1",
            status: "pending",
            payout: null,
            placedAt: new Date().toISOString(),
        };
    } else {
        const tipoff = Date.parse(req.body.tipoffUtc);
        const sevenDaysFromNow = Date.now() + 7 * 24 * 60 * 60 * 1000;
        if (!Number.isFinite(tipoff) || tipoff <= Date.now() || tipoff > sevenDaysFromNow) {
            return res.status(400).json({ success: false, message: "This NBA game is not open for betting in the next seven days." });
        }
        if (!new Set(["home", "away"]).has(selection)) {
            return res.status(400).json({ success: false, message: "Choose the home or away team." });
        }

        const homeTeam = String(req.body.homeTeam || "Home Team");
        const awayTeam = String(req.body.awayTeam || "Away Team");
        bet = {
            id: frontendTestState.nextBetId++,
            gameType: "real",
            gameId: String(req.body.gameId || ""),
            gameLabel: `${awayTeam} @ ${homeTeam}`,
            tipoffUtc: new Date(tipoff).toISOString(),
            selection,
            selectionLabel: selection === "home" ? homeTeam : awayTeam,
            amount,
            odds: "1:1",
            status: "pending",
            payout: null,
            placedAt: new Date().toISOString(),
        };
    }

    frontendTestState.balance = money(frontendTestState.balance - amount);
    frontendTestState.bets.unshift(bet);
    return res.status(201).json({ success: true, balance: frontendTestState.balance, bet });
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
