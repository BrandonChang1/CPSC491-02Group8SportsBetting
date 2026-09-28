const { AppError } = require("../errors");

/**
 * Catches requests that didn't match any route and returns the same
 * consistent error shape as everything else, instead of Express's default
 * HTML "Cannot GET /whatever" page.
 */
function notFoundHandler(req, res) {
  res.status(404).json({ error: { message: "Route not found" } });
}

/**
 * Centralized error handler — every route either throws/rejects an
 * AppError subclass (ValidationError, NotFoundError, ...) or lets an
 * unexpected error bubble up. Either way, the client always gets back
 * the same { error: { message } } shape, and unexpected errors are
 * logged server-side without leaking internals to the client.
 *
 * Must be registered last, after all routes (Express convention: an
 * error-handling middleware is recognized by having 4 parameters).
 */
function errorHandler(err, req, res, next) { // eslint-disable-line no-unused-vars
  if (err instanceof AppError) {
    return res.status(err.statusCode).json({ error: { message: err.message } });
  }

  console.error("Unhandled error:", err);
  res.status(500).json({ error: { message: "Internal server error" } });
}

module.exports = { notFoundHandler, errorHandler };
