"""Mesure les requêtes HTTP avec des labels de taille bornée."""
import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response

REQUESTS = Counter("bank_http_requests_total", "Requêtes HTTP", ["method", "route", "status"])
LATENCY = Histogram("bank_http_duration_seconds", "Durée HTTP", ["route"], buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2, 5, 10, 30))
REJECTIONS = Counter("bank_rejections_total", "Requêtes refusées par la validation, par motif", ["route", "motif"])
OUT_OF_RANGE = Counter("bank_out_of_range_clients_total", "Clients avec une valeur hors de celles du jeu de test", ["route"])
DRIFT_LEVEL = Gauge("bank_drift_level", "Écart avec le test historique : -1 effectif insuffisant, 0 faible, 1 modéré, 2 fort", ["campaign", "feature"])
CAMPAIGN_RATE = Gauge("bank_campaign_subscription_rate", "Taux de souscription du top 50 % des campagnes terminées", ["campaign"])


class MetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") == "/metrics":
            return await self.app(scope, receive, send)
        start, status = time.perf_counter(), 500

        async def wrapped_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            route = getattr(scope.get("route"), "path", "other")
            method = scope.get("method", "OTHER")
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
                method = "OTHER"
            REQUESTS.labels(method, route, str(status)).inc()
            LATENCY.labels(route).observe(time.perf_counter() - start)


def metrics_response():
    return Response(generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})
