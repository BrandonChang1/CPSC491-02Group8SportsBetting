/**
 * Custom error types used across the backend so every route can throw a
 * typed error instead of manually building a status code + JSON body each
 * time. The centralized error handler (backend/app/middleware/errorHandler.js)
 * knows how to translate these into a consistent response shape.
 */

class AppError extends Error {
  constructor(message, statusCode) {
    super(message);
    this.name = this.constructor.name;
    this.statusCode = statusCode;
  }
}

/** Bad input from the client: a malformed id, an out-of-range limit, etc. */
class ValidationError extends AppError {
  constructor(message) {
    super(message, 400);
  }
}

/** The requested resource doesn't exist. */
class NotFoundError extends AppError {
  constructor(message) {
    super(message, 404);
  }
}

module.exports = { AppError, ValidationError, NotFoundError };
