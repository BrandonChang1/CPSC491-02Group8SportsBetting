/**
 * Sprint 4 authentication tests (SEC-02, SOC 2 CC6.1 / CC6.2).
 *
 * Exercises the real register / login / me / logout routes against the real
 * Postgres database and checks the properties from the SEC-02 acceptance
 * criteria: passwords are stored only as scrypt hashes and never returned,
 * a wrong password and an unknown account get the same response, malformed
 * input is rejected with a safe error, the session cookie is HttpOnly and
 * SameSite=Lax, and logout revokes the session.
 *
 * All test accounts use the username prefix "sec02_auth_" and are removed
 * afterward.
 *
 * Run with: npm test
 */
const test = require("node:test");
const assert = require("node:assert");
const path = require("path");

require("dotenv").config({ path: path.join(__dirname, "..", "..", ".env") });

const express = require("express");
const request = require("supertest");

const pool = require("../app/db");
const { router: authRouter } = require("../app/routes/auth");
const { errorHandler } = require("../app/middleware/errorHandler");

const app = express();
app.use(express.json());
app.use(authRouter);
app.use(errorHandler);

const PREFIX = "sec02_auth_";
const MAIN_USER = `${PREFIX}main`;
const MAIN_EMAIL = `${PREFIX}main@example.com`;
const MAIN_PASSWORD = "correct-horse-battery";

async function cleanup() {
  await pool.query(
    "DELETE FROM user_sessions WHERE user_id IN (SELECT id FROM users WHERE username LIKE $1)",
    [`${PREFIX}%`]
  );
  await pool.query("DELETE FROM users WHERE username LIKE $1", [`${PREFIX}%`]);
}

/** Pulls "nba_session=<value>" out of a response's Set-Cookie header. */
function sessionCookie(res) {
  const header = res.headers["set-cookie"];
  assert.ok(header && header.length > 0, "expected a Set-Cookie header");
  return header[0].split(";")[0];
}

test.before(async () => {
  await cleanup();
  const res = await request(app)
    .post("/api/auth/register")
    .send({ username: MAIN_USER, email: MAIN_EMAIL, password: MAIN_PASSWORD });
  assert.strictEqual(res.status, 201);
});

test.after(async () => {
  await cleanup();
  await pool.end();
});

// --- registration and credential storage (criterion 4) -------------------

test("register with valid input returns 201 and never returns a password", async () => {
  const res = await request(app)
    .post("/api/auth/register")
    .send({ username: `${PREFIX}new`, email: `${PREFIX}new@example.com`, password: "another-long-password" });
  assert.strictEqual(res.status, 201);
  assert.strictEqual(res.body.success, true);
  const text = JSON.stringify(res.body);
  assert.ok(!text.includes("another-long-password"), "response must not echo the password");
  assert.ok(!/password_hash|hash/i.test(text), "response must not include a hash");
});

test("the password is stored only as a salted scrypt hash, never in plaintext", async () => {
  const { rows } = await pool.query("SELECT password_hash FROM users WHERE username = $1", [MAIN_USER]);
  assert.strictEqual(rows.length, 1);
  const stored = rows[0].password_hash;
  assert.ok(stored.startsWith("scrypt:"), "expected a scrypt hash");
  assert.strictEqual(stored.split(":").length, 3, "expected scrypt:<salt>:<hash>");
  assert.ok(!stored.includes(MAIN_PASSWORD), "plaintext password must not be stored");
});

test("registering an existing username is rejected with 409", async () => {
  const res = await request(app)
    .post("/api/auth/register")
    .send({ username: MAIN_USER, email: `${PREFIX}other@example.com`, password: "some-long-password" });
  assert.strictEqual(res.status, 409);
  assert.strictEqual(res.body.success, false);
});

// --- login and cookie flags (criteria 5 and 6) ---------------------------

test("login with the correct password sets an HttpOnly, SameSite=Lax session cookie", async () => {
  const res = await request(app)
    .post("/api/auth/login")
    .send({ identifier: MAIN_USER, password: MAIN_PASSWORD });
  assert.strictEqual(res.status, 200);
  assert.strictEqual(res.body.success, true);

  const cookie = res.headers["set-cookie"].join("; ");
  assert.ok(cookie.includes("nba_session="), "expected the nba_session cookie");
  assert.ok(cookie.includes("HttpOnly"), "cookie must be HttpOnly");
  assert.ok(cookie.includes("SameSite=Lax"), "cookie must be SameSite=Lax");

  const text = JSON.stringify(res.body);
  assert.ok(!text.includes(MAIN_PASSWORD) && !/password_hash/i.test(text), "login must not return credentials");
});

test("a wrong password and an unknown account get the same 401 response", async () => {
  const wrongPassword = await request(app)
    .post("/api/auth/login")
    .send({ identifier: MAIN_USER, password: "not-the-password" });
  const unknownAccount = await request(app)
    .post("/api/auth/login")
    .send({ identifier: `${PREFIX}does_not_exist`, password: "not-the-password" });

  assert.strictEqual(wrongPassword.status, 401);
  assert.strictEqual(unknownAccount.status, 401);
  assert.deepStrictEqual(wrongPassword.body, unknownAccount.body);
  assert.strictEqual(wrongPassword.headers["set-cookie"], undefined, "no cookie on a failed login");
});

// --- malformed input (criterion 7) ---------------------------------------

for (const [label, body] of [
  ["a too-short username", { username: "ab", email: `${PREFIX}x@example.com`, password: "long-enough-pw" }],
  ["an invalid email", { username: `${PREFIX}badmail`, email: "not-an-email", password: "long-enough-pw" }],
  ["a too-short password", { username: `${PREFIX}shortpw`, email: `${PREFIX}y@example.com`, password: "short" }],
]) {
  test(`register rejects ${label} with 400 and a safe error`, async () => {
    const res = await request(app).post("/api/auth/register").send(body);
    assert.strictEqual(res.status, 400);
    assert.strictEqual(res.body.success, false);
    assert.deepStrictEqual(Object.keys(res.body).sort(), ["message", "success"], "no extra fields or stack trace");
  });
}

test("login with missing fields returns 400", async () => {
  const res = await request(app).post("/api/auth/login").send({ identifier: MAIN_USER });
  assert.strictEqual(res.status, 400);
  assert.strictEqual(res.body.success, false);
});

// --- session lifecycle (criterion 3) -------------------------------------

test("a session from login works for /me, and logout revokes it", async () => {
  const login = await request(app)
    .post("/api/auth/login")
    .send({ identifier: MAIN_USER, password: MAIN_PASSWORD });
  const cookie = sessionCookie(login);

  const me = await request(app).get("/api/auth/me").set("Cookie", cookie);
  assert.strictEqual(me.status, 200);
  assert.strictEqual(me.body.user.username, MAIN_USER);
  assert.ok(!JSON.stringify(me.body).includes("password"), "/me must not expose credentials");

  const logout = await request(app).post("/api/auth/logout").set("Cookie", cookie);
  assert.strictEqual(logout.status, 200);

  const replay = await request(app).get("/api/auth/me").set("Cookie", cookie);
  assert.strictEqual(replay.status, 401);
});