const crypto = require("crypto");
const express = require("express");
const { Pool } = require("pg");

const router = express.Router();

const pool = new Pool({
    connectionString: process.env.DATABASE_URL,
});

const SESSION_COOKIE = "nba_session";
const SESSION_DAYS = 7;
const SESSION_MAX_AGE_MS = SESSION_DAYS * 24 * 60 * 60 * 1000;

function parseCookies(cookieHeader = "") {
    const cookies = {};

    for (const pair of cookieHeader.split(";")) {
        const separatorIndex = pair.indexOf("=");
        if (separatorIndex === -1) {
            continue;
        }

        const key = pair.slice(0, separatorIndex).trim();
        const value = pair.slice(separatorIndex + 1).trim();

        if (key) {
            cookies[key] = decodeURIComponent(value);
        }
    }

    return cookies;
}

function normalizeEmail(email) {
    return String(email || "").trim().toLowerCase();
}

function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function hashSessionToken(token) {
    return crypto.createHash("sha256").update(token).digest("hex");
}

function scryptAsync(password, salt) {
    return new Promise((resolve, reject) => {
        crypto.scrypt(password, salt, 64, (error, derivedKey) => {
            if (error) {
                reject(error);
                return;
            }
            resolve(derivedKey);
        });
    });
}

async function hashPassword(password) {
    const salt = crypto.randomBytes(16).toString("hex");
    const derivedKey = await scryptAsync(password, salt);
    return `scrypt:${salt}:${derivedKey.toString("hex")}`;
}

async function verifyPassword(password, storedHash) {
    const [algorithm, salt, expectedHex] = String(storedHash || "").split(":");

    if (algorithm !== "scrypt" || !salt || !expectedHex) {
        return false;
    }

    const actual = await scryptAsync(password, salt);
    const expected = Buffer.from(expectedHex, "hex");

    if (actual.length !== expected.length) {
        return false;
    }

    return crypto.timingSafeEqual(actual, expected);
}

function setSessionCookie(res, rawToken) {
    const securePart = process.env.NODE_ENV === "production" ? "; Secure" : "";

    res.setHeader(
        "Set-Cookie",
        `${SESSION_COOKIE}=${encodeURIComponent(rawToken)}; HttpOnly; Path=/; SameSite=Lax; Max-Age=${Math.floor(SESSION_MAX_AGE_MS / 1000)}${securePart}`
    );
}

function clearSessionCookie(res) {
    const securePart = process.env.NODE_ENV === "production" ? "; Secure" : "";

    res.setHeader(
        "Set-Cookie",
        `${SESSION_COOKIE}=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0${securePart}`
    );
}

async function createSession(userId, res) {
    const rawToken = crypto.randomBytes(32).toString("hex");
    const tokenHash = hashSessionToken(rawToken);

    await pool.query(
        `INSERT INTO user_sessions (user_id, token_hash, expires_at)
         VALUES ($1, $2, NOW() + INTERVAL '${SESSION_DAYS} days')`,
        [userId, tokenHash]
    );

    setSessionCookie(res, rawToken);
}

async function getUserFromRequest(req) {
    const cookies = parseCookies(req.headers.cookie);
    const rawToken = cookies[SESSION_COOKIE];

    if (!rawToken) {
        return null;
    }

    const tokenHash = hashSessionToken(rawToken);

    const result = await pool.query(
        `SELECT u.id, u.username, u.email, u.created_at
         FROM user_sessions s
         JOIN users u ON u.id = s.user_id
         WHERE s.token_hash = $1
           AND s.expires_at > NOW()
         LIMIT 1`,
        [tokenHash]
    );

    return result.rows[0] || null;
}

async function requireAuth(req, res, next) {
    try {
        const user = await getUserFromRequest(req);

        if (!user) {
            return res.status(401).json({
                success: false,
                message: "You must be logged in to access this page.",
            });
        }

        req.user = user;
        return next();
    } catch (error) {
        return next(error);
    }
}

router.post("/api/auth/register", async (req, res, next) => {
    try {
        const username = String(req.body.username || "").trim();
        const email = normalizeEmail(req.body.email);
        const password = String(req.body.password || "");

        if (username.length < 3 || username.length > 30) {
            return res.status(400).json({
                success: false,
                message: "Username must be between 3 and 30 characters.",
            });
        }

        if (!isValidEmail(email)) {
            return res.status(400).json({
                success: false,
                message: "Enter a valid email address.",
            });
        }

        if (password.length < 8) {
            return res.status(400).json({
                success: false,
                message: "Password must be at least 8 characters long.",
            });
        }

        const duplicate = await pool.query(
            `SELECT username, email
             FROM users
             WHERE LOWER(username) = LOWER($1)
                OR LOWER(email) = LOWER($2)
             LIMIT 1`,
            [username, email]
        );

        if (duplicate.rows.length > 0) {
            const existing = duplicate.rows[0];
            const usernameTaken = existing.username.toLowerCase() === username.toLowerCase();

            return res.status(409).json({
                success: false,
                message: usernameTaken
                    ? "That username is already taken."
                    : "An account already exists with that email address.",
            });
        }

        const passwordHash = await hashPassword(password);

        await pool.query(
            `INSERT INTO users (username, email, password_hash)
             VALUES ($1, $2, $3)`,
            [username, email, passwordHash]
        );

        return res.status(201).json({
            success: true,
            message: "Account created successfully. You can now log in.",
        });
    } catch (error) {
        if (error.code === "23505") {
            return res.status(409).json({
                success: false,
                message: "That username or email is already in use.",
            });
        }

        return next(error);
    }
});

router.post("/api/auth/login", async (req, res, next) => {
    try {
        const identifier = String(req.body.identifier || "").trim();
        const password = String(req.body.password || "");

        if (!identifier || !password) {
            return res.status(400).json({
                success: false,
                message: "Username/email and password are required.",
            });
        }

        const result = await pool.query(
            `SELECT id, username, email, password_hash
             FROM users
             WHERE LOWER(username) = LOWER($1)
                OR LOWER(email) = LOWER($1)
             LIMIT 1`,
            [identifier]
        );

        const user = result.rows[0];

        if (!user || !(await verifyPassword(password, user.password_hash))) {
            return res.status(401).json({
                success: false,
                message: "Incorrect username/email or password.",
            });
        }

        await pool.query(
            "DELETE FROM user_sessions WHERE expires_at <= NOW()"
        );

        await createSession(user.id, res);

        return res.json({
            success: true,
            message: "Login successful.",
            user: {
                id: user.id,
                username: user.username,
                email: user.email,
            },
        });
    } catch (error) {
        return next(error);
    }
});

router.get("/api/auth/me", async (req, res, next) => {
    try {
        const user = await getUserFromRequest(req);

        if (!user) {
            return res.status(401).json({
                success: false,
                message: "Not logged in.",
            });
        }

        return res.json({
            success: true,
            user,
        });
    } catch (error) {
        return next(error);
    }
});

router.post("/api/auth/logout", async (req, res, next) => {
    try {
        const cookies = parseCookies(req.headers.cookie);
        const rawToken = cookies[SESSION_COOKIE];

        if (rawToken) {
            await pool.query(
                "DELETE FROM user_sessions WHERE token_hash = $1",
                [hashSessionToken(rawToken)]
            );
        }

        clearSessionCookie(res);

        return res.json({
            success: true,
            message: "Logged out successfully.",
        });
    } catch (error) {
        return next(error);
    }
});

module.exports = {
    router,
    requireAuth,
};
