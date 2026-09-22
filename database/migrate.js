/**
 * Minimal migration runner.
 *
 * Applies every .sql file in database/migrations/, in filename order,
 * exactly once. A schema_migrations table records which files have
 * already run so `npm run migrate` is safe to run repeatedly (e.g. in
 * CI, or every time a teammate pulls new migration files).
 *
 * Usage: npm run migrate
 */
require("dotenv").config();
const fs = require("fs");
const path = require("path");
const { Pool } = require("pg");

const MIGRATIONS_DIR = path.join(__dirname, "migrations");

async function run() {
  const pool = new Pool({ connectionString: process.env.DATABASE_URL });

  try {
    // Tracks which migration files have already been applied.
    await pool.query(`
      CREATE TABLE IF NOT EXISTS schema_migrations (
        filename VARCHAR(255) PRIMARY KEY,
        applied_at TIMESTAMP NOT NULL DEFAULT NOW()
      )
    `);

    const { rows } = await pool.query("SELECT filename FROM schema_migrations");
    const applied = new Set(rows.map((r) => r.filename));

    const files = fs
      .readdirSync(MIGRATIONS_DIR)
      .filter((f) => f.endsWith(".sql"))
      .sort(); // filenames are numbered (001_, 002_, ...) so lexical sort = order

    for (const file of files) {
      if (applied.has(file)) {
        console.log(`skip  ${file} (already applied)`);
        continue;
      }

      const sql = fs.readFileSync(path.join(MIGRATIONS_DIR, file), "utf8");
      console.log(`apply ${file}`);

      // Run the migration and record it in the same transaction, so a
      // failed migration never gets marked as applied.
      const client = await pool.connect();
      try {
        await client.query("BEGIN");
        await client.query(sql);
        await client.query("INSERT INTO schema_migrations (filename) VALUES ($1)", [file]);
        await client.query("COMMIT");
      } catch (err) {
        await client.query("ROLLBACK");
        throw new Error(`Migration ${file} failed: ${err.message}`);
      } finally {
        client.release();
      }
    }

    console.log("Migrations up to date.");
  } finally {
    await pool.end();
  }
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
