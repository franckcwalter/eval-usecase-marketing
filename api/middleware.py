"""Journalise chaque requête : méthode, route, statut, latence et identifiant de requête."""
import time
import uuid

from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.bind(request_id=request_id).exception("Erreur non gérée")
            raise

        status = response.status_code
        logger.bind(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=status,
            latency_ms=round((time.perf_counter() - start) * 1000, 2),
        ).log(
            "INFO" if status < 400 else "WARNING" if status < 500 else "ERROR",
            "{} {} {}", request.method, request.url.path, status,
        )
        response.headers["X-Request-ID"] = request_id
        return response
