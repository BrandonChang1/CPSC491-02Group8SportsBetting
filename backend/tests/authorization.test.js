/**
 * Sprint 5 backend authorization and negative-path sweep (SCRUM-73).
 *
 * Runs the same set of negative checks against EVERY route that requires a
 * login (SEC-02, SOC 2 CC6.1 / CC6.2) and confirms they all behave the same:
 *
 *   - no cookie, an empty cookie, garbage, injection-style and oversized
 *     cookie values, a valid token under the wrong cookie name, and a valid
 *     token sent as a Bearer header are all rejected with 401, never 500
 *   - an expired session and a revoked (logged-out) session are rejected
 *   - a valid session is let through
 *   - authentication is checked BEFORE validation and lookup, so a caller who
 *     is not logged in gets 401 and never learns whether an id exists (404)
 *     or is malformed (400)
 *   - the app has no roles, so 403 is never returned
 *   - unknown routes and wrong methods get the shared 404 error shape
 *
 * One test is marked `todo`: /api/players/:id/prediction is currently NOT
 * protected. It documents the gap and will start passing once the route is
 * given requireAuth.
 *
 * A fake user is seeded and removed afterward. No player data is needed.
 *
 * Run with: npm test
 */
const test = require("node:test");
const assert = require("node:assert");
const path = require("path");
const crypto = require("crypto");

require("dotenv").config({ path: path.join(__dirname, "..", "..", ".env") });

const express = require("express");
const request = require("supertest");

const pool = require("../app/db");
const playersRouter = require("../app/routes/players");
const predictionsRouter = require("../app/routes/predictions");
const { router: authRouter } = require("../app/routes/auth");
const { notFoundHandler, errorHandler } = require("../app/middleware/errorHandler");

const app = express();
app.use(express.json());
app.use(authRouter);
app.use(playersRouter);
app.use(predictionsRouter);
app.use(notFoundHandler);
app.use(errorHandler);

// Every route that requires a login. `url` points at an id that does not
// exist, so a request that gets past authentication returns 404 (or 200 for
// routes with no id), which is never 401.
const PROTECTED = [
  { name: "prediction", url: "/players/9300001/prediction", badIdUrl: "/players/abc/prediction", sharedBody: true },
  { name: "trends", url: "/players/9300001/trends", badIdUrl: "/players/abc/trends", sharedBody: true },
  { name: "model metrics", url: "/models/metrics", badIdUrl: null, sharedBody: true },
  { name: "current user (/me)", url: "/api/auth/me", badIdUrl: null, sharedBody: false },
];

// --- fixtures -------------------------------------------------------------
const USER_NAME = "scrum73_authz_user";
const USER_EMAIL = "scrum73_authz_user@example.com";
const hashToken = (token) => crypto.createHash("sha256").update(token).digest("hex");
let userId;

async function cleanupUser() {
  await pool.query(
    "DELETE FROM user_sessions WHERE user_id IN (SELECT id FROM users WHERE username = $1)",
    [USER_NAME]
  );
  await pool.query("DELETE FROM users WHERE username = $1", [USER_NAME]);
}

/** Creates a session for the test user and returns its raw token. */
async function newSession(interval = "1 day") {
  const raw = crypto.randomBytes(32).toString("hex");
  await pool.query(
    `INSERT INTO user_sessions (user_id, token_hash, expires_at)
     VALUES ($1, $2, NOW() + $3::interval)`,
    [userId, hashToken(raw), interval]
  );
  return raw;
}

const withCookie = (url, cookie) => request(app).get(url).set("Cookie", cookie);

test.before(async () => {
  await cleanupUser();
  const user = await pool.query(
    `INSERT INTO users (username, email, password_hash)
     VALUES ($1, $2, 'scrypt:test:test') RETURNING id`,
    [USER_NAME, USER_EMAIL]
  );
  userId = user.rows[0].id;
});

test.after(async () => {
  await cleanupUser();
  await pool.end();
});

// --- the same negative-path checks for every protected route ---------------

for (const route of PROTECTED) {
  test(`${route.name}: no cookie returns 401`, async () => {
    const res = await request(app).get(route.url);
    assert.strictEqual(res.status, 401);
  });

  test(`${route.name}: malformed, injection-style and oversized cookies return 401, never 500`, async () => {
    const valid = await newSession();
    const variants = [
      "nba_session=",
      "nba_session=garbage",
      "nba_session=' OR '1'='1",
      "nba_session=%00",
      `nba_session=${"a".repeat(5000)}`,
      `session=${valid}`, // a real token, but under the wrong cookie name
    ];
    for (const cookie of variants) {
      const res = await withCookie(route.url, cookie);
      assert.strictEqual(res.status, 401, `cookie "${cookie.slice(0, 40)}" should be rejected with 401`);
    }
  });

  test(`${route.name}: an expired session returns 401`, async () => {
    const raw = await newSession("-1 hour");
    const res = await withCookie(route.url, `nba_session=${raw}`);
    assert.strictEqual(res.status, 401);
  });

  test(`${route.name}: a revoked session returns 401`, async () => {
    const raw = await newSession();
    await pool.query("DELETE FROM user_sessions WHERE token_hash = $1", [hashToken(raw)]);
    const res = await withCookie(route.url, `nba_session=${raw}`);
    assert.strictEqual(res.status, 401);
  });

  test(`${route.name}: a valid token sent as a Bearer header is not accepted`, async () => {
    const raw = await newSession();
    const res = await request(app).get(route.url).set("Authorization", `Bearer ${raw}`);
    assert.strictEqual(res.status, 401, "sessions are accepted only through the cookie");
  });

  test(`${route.name}: a valid session gets past authentication (never 401 or 403)`, async () => {
    const raw = await newSession();
    const res = await withCookie(route.url, `nba_session=${raw}`);
    assert.notStrictEqual(res.status, 401);
    assert.notStrictEqual(res.status, 403, "the app has no roles, so 403 must never be returned");
  });

  if (route.badIdUrl) {
    test(`${route.name}: authentication is checked before validation and lookup`, async () => {
      // Not logged in: a malformed id and an unknown id both give 401, not 400 or 404.
      const malformed = await request(app).get(route.badIdUrl);
      assert.strictEqual(malformed.status, 401, "must not reveal that the id is malformed");
      const unknown = await request(app).get(route.url);
      assert.strictEqual(unknown.status, 401, "must not reveal whether the id exists");

      // Logged in: the same requests now reach validation (400) and lookup (404).
      const raw = await newSession();
      const loggedInMalformed = await withCookie(route.badIdUrl, `nba_session=${raw}`);
      assert.strictEqual(loggedInMalformed.status, 400);
      const loggedInUnknown = await withCookie(route.url, `nba_session=${raw}`);
      assert.strictEqual(loggedInUnknown.status, 404);
    });
  }
}

test("every requireAuth route rejects with the same 401 body", async () => {
  const bodies = [];
  for (const route of PROTECTED.filter((r) => r.sharedBody)) {
    const res = await request(app).get(route.url);
    assert.strictEqual(res.status, 401);
    assert.strictEqual(res.body.success, false);
    bodies.push(res.body);
  }
  for (const body of bodies) {
    assert.deepStrictEqual(body, bodies[0], "401 responses must be identical across routes");
  }
});

// --- other negative paths -------------------------------------------------

test("an unknown route returns 404 with the shared error shape", async () => {
  const res = await request(app).get("/this/route/does/not/exist");
  assert.strictEqual(res.status, 404);
  assert.deepStrictEqual(res.body, { error: { message: "Route not found" } });
});

test("the wrong HTTP method on a protected route returns the shared 404, not a 500", async () => {
  const res = await request(app).post("/players/9300001/trends");
  assert.strictEqual(res.status, 404);
  assert.deepStrictEqual(res.body, { error: { message: "Route not found" } });
});

// --- known gaps ---------------------------------------------------------

test(
  "a cookie with broken percent-encoding returns 401, not 500 (KNOWN GAP in auth.js parseCookies)",
  { todo: "SCRUM-73 finding: parseCookies calls decodeURIComponent without try/catch, so %E0%A4%A gives a 500" },
  async () => {
    for (const route of PROTECTED) {
      const res = await withCookie(route.url, "nba_session=%E0%A4%A");
      assert.strictEqual(res.status, 401, `${route.name} should return 401`);
    }
  }
);

test(
  "GET /api/players/:id/prediction requires a login (KNOWN GAP: route has no requireAuth yet)",
  { todo: "SCRUM-73 finding: /api/players/:id/prediction is public, unlike /players/:id/prediction" },
  async () => {
    // A malformed id is used so the check is fast and never reaches the model.
    const res = await request(app).get("/api/players/abc/prediction");
    assert.strictEqual(res.status, 401);
  }
);