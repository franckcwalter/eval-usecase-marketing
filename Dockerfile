FROM python:3.12-slim

RUN useradd --create-home --shell /bin/bash --uid 1000 appuser
WORKDIR /home/appuser/app

COPY --chown=appuser:appuser api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r api/requirements.txt

COPY --chown=appuser:appuser api/ api/
COPY --chown=appuser:appuser training/__init__.py training/pipeline.py training/retrain.py training/
COPY --chown=appuser:appuser monitoring/__init__.py monitoring/campaigns.py monitoring/drift.py monitoring/
COPY --chown=appuser:appuser evaluation/__init__.py evaluation/core.py evaluation/golden.json evaluation/reference.csv evaluation/
COPY --chown=appuser:appuser models/ models/
COPY --chown=appuser:appuser frontend/ frontend/
RUN mkdir logs storage && chown appuser:appuser logs storage

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
