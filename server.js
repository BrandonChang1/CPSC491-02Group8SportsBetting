const express = require("express");
const { execFile } = require("child_process");
const path = require("path");

const app = express();
const PORT = 3000;

app.use(express.static(path.join(__dirname, "public")));

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

<<<<<<< Updated upstream
    execFile(
        "python",
        [scriptPath, team],
=======
function runPythonScript(scriptPath, args, res) {
    const pythonCommand = process.env.PYTHON_COMMAND || "python";

    execFile(
        pythonCommand,
        [scriptPath, ...args],
>>>>>>> Stashed changes
        (error, stdout, stderr) => {

            if (error) {
                console.error("Python error:", error);

                return res.status(500).json({
                    success: false,
                    message: stderr || error.message,
                    data: []
                });
            }

            try {

                const result = JSON.parse(stdout);

                res.json(result);

            } catch (parseError) {

                console.error(
                    "Could not parse Python output:",
                    parseError
                );

                res.status(500).json({
                    success: false,
                    message: "Python returned invalid JSON.",
                    data: []
                });
            }
        }
    );
});

<<<<<<< Updated upstream
=======

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


>>>>>>> Stashed changes
app.listen(PORT, () => {
    console.log(
        `Server running at http://localhost:${PORT}`
    );
});