FROM python:3.12-slim
ENV GIT_PYTHON_REFRESH=quiet
ENV MLFLOW_DISABLE_AGENT_HINT=1
WORKDIR /app
COPY api/requirements.txt api/requirements.txt
COPY monitoring/requirements.txt monitoring/requirements.txt
RUN pip install --no-cache-dir -r monitoring/requirements.txt
RUN useradd --uid 1000 --create-home appuser && mkdir /tracking && chown appuser:appuser /tracking
USER appuser
CMD ["mlflow", "server", "--host", "0.0.0.0", "--port", "5000", "--backend-store-uri", "sqlite:////tracking/mlflow.db", "--artifacts-destination", "/tracking/artifacts", "--allowed-hosts", "mlflow:5000,localhost:5000,127.0.0.1:5000"]
