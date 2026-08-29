FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY data_pipeline ./data_pipeline
COPY ml ./ml
RUN pip install --no-cache-dir .
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app

EXPOSE 8000
USER appuser
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
