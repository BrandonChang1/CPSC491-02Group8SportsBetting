const express = require("express");
const { execFile } = require("child_process");
const path = require("path");

const healthRouter = require("./backend/app/routes/health");
const playersRouter = require("./backend/app/routes/players");

const app = express();
const PORT = process.env.PORT || 3000;
const PYTHON_COMMAND = process.env.PYTHON_COMMAND || (process.platform === "win32" ? "python" : "python3");

app.use(express.static(path.join(__dirname, "public")));
app.use(healthRouter);
app.use(playersRouter);


function runPythonScript(scriptPath, args, res) {
    execFile(
        PYTHON_COMMAND,
        [scriptPath, ...args],
        (error, stdout, stderr) => {
            // The Python helpers return JSON on stdout, including controlled
            // error responses. Parse that output first so the browser receives
            // a useful message instead of only a child-process exit error.
            if (stdout && stdout.trim()) {
                try {
                    const result = JSON.parse(stdout);
                    return res.status(error ? 502 : 200).json(result);
                } catch (parseError) {
                    console.error("Could not parse Python output:", parseError);
                }
            }

            if (error) {
                console.error("Python error:", error);

                return res.status(500).json({
                    success: false,
                    message: (stderr && stderr.trim()) || error.message,
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

    runPythonScript(scriptPath, [team], res);
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

    runPythonScript(
        scriptPath,
        ["search", query.trim()],
        res
    );
});


app.get("/player-stats", (req, res) => {
    const playerId = req.query.id;

    if (!playerId) {
        return res.status(400).json({
            success: false,
            message: "No player ID was provided.",
            data: []
        });
    }

    const scriptPath = path.join(
        __dirname,
        "scripts",
        "webpage_player_search.py"
    );

    runPythonScript(
        scriptPath,
        ["stats", playerId],
        res
    );
});


app.get("/api/upcoming-games", (req, res) => {
    const scriptPath = path.join(
        __dirname,
        "scripts",
        "upcoming_games.py"
    );

    runPythonScript(scriptPath, [], res);
});


app.listen(PORT, () => {
    console.log(
        `Server running at http://localhost:${PORT}`
    );
});