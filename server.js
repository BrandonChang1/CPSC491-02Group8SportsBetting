const express = require("express");
const { exec } = require("child_process");
const path = require("path");

const app = express();
const PORT = 3000;

app.use(express.static(path.join(__dirname, "public")));

app.get("/run-test", (req, res) => {
    exec("python Test.py", (error, stdout, stderr) => {
        if (error) {
            console.error("Test failed:", error);

            return res.status(500).json({
                success: false,
                message: stderr || error.message
            });
        }

        res.json({
            success: true,
            message: stdout || "Test completed successfully."
        });
    });
});

app.listen(PORT, () => {
    console.log(`Server running at http://localhost:${PORT}`);
});