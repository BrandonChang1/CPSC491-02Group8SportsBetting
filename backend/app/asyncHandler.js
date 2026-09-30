/**
 * Express route handlers that are `async` can throw/reject without Express
 * ever seeing it — the request just hangs. Wrapping a handler in this
 * catches that rejection and forwards it to next(err), so it reaches the
 * centralized error handler like any other error.
 */
function asyncHandler(fn) {
  return (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next);
}

module.exports = asyncHandler;
