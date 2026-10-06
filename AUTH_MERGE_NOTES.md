# Local Authentication Merge

This patch integrates account registration and login into the existing Express + PostgreSQL project without adding any new npm dependencies.

## What changed

- `server.js`
  - Loads `.env` through `dotenv`.
  - Enables `express.json()` for auth request bodies.
  - Registers the new auth router.
  - Adds a protected `/app` page.
  - Exports the Express app so it remains testable with Supertest.
- `backend/app/routes/auth.js`
  - `POST /api/auth/register`
  - `POST /api/auth/login`
  - `GET /api/auth/me`
  - `POST /api/auth/logout`
  - Passwords are hashed with Node's built-in `crypto.scrypt`.
  - Sessions use random opaque tokens. Only a SHA-256 hash of the token is stored in PostgreSQL.
  - The browser receives an HttpOnly, SameSite=Lax cookie.
- `database/migrations/900_create_auth.sql`
  - Adds `users` and `user_sessions` tables.
- `public/create-account.html`
  - Sends account data to `/api/auth/register`.
- `public/login.html`
  - Logs in through `/api/auth/login` and redirects to `/app`.
- `protected/home.html`
  - Shows the logged-in username/email and includes logout plus links to the existing NBA pages.
- `public/index.html`
  - Adds Login and Logged-In App buttons while retaining the existing project navigation.

## Merge into the repository

Copy the files in this patch into the repository root while preserving the included paths.

The patch assumes the existing project still contains these files referenced by `server.js`:

- `backend/app/routes/health.js`
- `backend/app/routes/players.js`
- `backend/app/middleware/errorHandler.js`
- the existing `database/migrate.js`
- the existing Python scripts under `scripts/`

Those existing project files are intentionally not replaced by this patch.

## Local setup

1. Make sure PostgreSQL is running and the `.env` file contains a working `DATABASE_URL`.
2. Install the existing project dependencies:

   ```bash
   npm install
   ```

3. Apply migrations:

   ```bash
   npm run migrate
   ```

4. Start the server:

   ```bash
   npm start
   ```

5. Open `http://localhost:3000/create-account.html`, create an account, then log in.

## Database tables

The migration creates:

- `users`: username, email, password hash, created timestamp.
- `user_sessions`: hashed session token, user id, expiry timestamp.

No plaintext password or plaintext session token is stored in PostgreSQL.
