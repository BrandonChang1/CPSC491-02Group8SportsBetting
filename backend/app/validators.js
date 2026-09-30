/**
 * Shared query-param validation, so every list/detail endpoint enforces
 * the same rules instead of each route hand-rolling its own checks.
 */
const { ValidationError } = require("./errors");

/**
 * Reads `skip`/`limit` off req.query, validates them, and returns sane
 * integers. Throws ValidationError (→ 400) on anything malformed.
 */
function parsePagination(query, { defaultLimit = 50, maxLimit = 200 } = {}) {
  let skip = 0;
  let limit = defaultLimit;

  if (query.skip !== undefined) {
    skip = Number(query.skip);
    if (!Number.isInteger(skip) || skip < 0) {
      throw new ValidationError("skip must be a non-negative integer");
    }
  }

  if (query.limit !== undefined) {
    limit = Number(query.limit);
    if (!Number.isInteger(limit) || limit <= 0) {
      throw new ValidationError("limit must be a positive integer");
    }
  }

  if (limit > maxLimit) {
    throw new ValidationError(`limit cannot exceed ${maxLimit}`);
  }

  return { skip, limit };
}

/**
 * Validates a route param (e.g. :id) is a whole number, since Postgres
 * will otherwise throw its own less-readable error on a bad integer cast.
 */
function parseIntParam(value, name) {
  const n = Number(value);
  if (!Number.isInteger(n)) {
    throw new ValidationError(`${name} must be an integer`);
  }
  return n;
}

module.exports = { parsePagination, parseIntParam };
