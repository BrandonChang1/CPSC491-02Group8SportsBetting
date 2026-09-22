/**
 * Shared PostgreSQL connection pool.
 *
 * `pg`'s Pool manages a set of reusable connections rather than opening a
 * new one per request, which is what you want under real traffic. Every
 * route imports `pool` from here instead of creating its own connection.
 */
require("dotenv").config();
const { Pool } = require("pg");

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});

module.exports = pool;
