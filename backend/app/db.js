/**
 * Shared PostgreSQL connection pool.
 *
 * `pg`'s Pool manages a set of reusable connections rather than opening a
 * new one per request, which is what you want under real traffic. Every
 * route imports `pool` from here instead of creating its own connection.
 */
require("dotenv").config();
const { Pool, types } = require("pg");

// By default, node-postgres returns BIGINT (OID 20) columns as strings,
// because a 64-bit value can exceed what JS can represent exactly as a
// number. Our BIGINT columns (players.id, teams.id) hold real-world NBA
// ids, which are nowhere near that range, so parsing them as plain JS
// numbers is safe here and much less error-prone for callers than having
// ids silently switch between number and string depending on the column.
types.setTypeParser(20, (value) => parseInt(value, 10));

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});

module.exports = pool;
