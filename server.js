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

    execFile(
        "python",
        ["Test.py", team],
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