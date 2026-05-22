FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

RUN addgroup --system tripsplit \
    && adduser --system --ingroup tripsplit --home /app tripsplit \
    && mkdir -p /data \
    && chown -R tripsplit:tripsplit /app /data

USER tripsplit

CMD ["python", "-m", "tripsplitexpenses"]
