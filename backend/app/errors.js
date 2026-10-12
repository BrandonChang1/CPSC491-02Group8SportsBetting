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

/** The request is valid but there isn't enough data to fulfil it (e.g. a player with no games to predict from). */
class InsufficientDataError extends AppError {
  constructor(message) {
    super(message, 422);
  }
}

/** The prediction model could not be reached or failed while running. */
class ModelUnavailableError extends AppError {
  constructor(message) {
    super(message, 503);
  }
}

/** The prediction model ran but returned something that isn't a usable result. */
class ModelOutputError extends AppError {
  constructor(message) {
    super(message, 502);
  }
}

module.exports = {
  AppError,
  ValidationError,
  NotFoundError,
  InsufficientDataError,
  ModelUnavailableError,
  ModelOutputError,
};
