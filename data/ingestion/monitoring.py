"""Credential-safe diagnostics and exit status for ingestion commands."""

import logging

import psycopg
import requests

logger = logging.getLogger("data.ingestion")


def run(main):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        return main() or 0
    except (
        requests.RequestException, psycopg.Error, ValueError, KeyError,
        TypeError, RuntimeError, IndexError,
    ) as error:
        # Exception messages and tracebacks can contain database URLs or request headers.
        logger.error("ingestion_failed command=%s error_type=%s", main.__module__, type(error).__name__)
        return 1
