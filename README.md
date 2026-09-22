# CPSC491-02Group8SportsBetting

## Basic running instructions<br>
Step 1 - Make sure both NodeJS and Express are installed locally, once NodeJS is installed, run this command to install express: "npm init -y
npm install express"<br>
Step 2 - Make sure to have all required python libraries installed, you can do this by running the command "pip install nba_api pandas sqlalchemy pymysql"<br>
Step 3 - Clone Repo and open Command Line in Repo folder<br>
Step 4 - Run the command "node server.js"<br>
Step 5 - Open the window at "[http:localhost:3000]"<br>
Step 6 - Enjoy!<br>

## Upcoming NBA games
The home page includes a **View Upcoming NBA Games** button. The page calls `GET /api/upcoming-games`, and the Express server runs `scripts/upcoming_games.py` to retrieve the NBA season schedule through `nba_api.stats.endpoints.scheduleleaguev2.ScheduleLeagueV2`. The response is filtered to scheduled games whose tipoff is within the next 14 days.

Install dependencies before running the project:

```powershell
npm install
python -m pip install -r requirements.txt
node server.js
```

Then open `http://localhost:3000` and choose **View Upcoming NBA Games**.

The schedule script uses nba_api's dictionary output instead of pandas DataFrames, so the upcoming-games feature itself does not import pandas.

If Windows uses a different Python executable, set `PYTHON_COMMAND` before starting Node. For example:

```powershell
$env:PYTHON_COMMAND = "py"
node server.js
```
