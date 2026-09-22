const express = require("express");
const { execFile } = require("child_process");
const path = require("path");

const healthRouter = require("./backend/app/routes/health");
const playersRouter = require("./backend/app/routes/players");

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.static(path.join(__dirname, "public")));
app.use(healthRouter);
app.use(playersRouter);

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

    execFile(
        "python",
        [scriptPath, team],
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

app.listen(PORT, () => {
    console.log(
        `Server running at http://localhost:${PORT}`
    );
});