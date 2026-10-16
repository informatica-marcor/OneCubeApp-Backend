FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
# psycopg2 se compila contra libpq, sin cambiar las dependencias existentes.
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip wheel --wheel-dir=/wheels -r requirements.txt

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ROOT=/data
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 onecube \
    && mkdir -p /data/uploads /data/logs /data/assets \
    && chown -R onecube:onecube /data
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && rm -rf /wheels
COPY --chown=onecube:onecube app ./app
COPY --chown=onecube:onecube alembic ./alembic
COPY --chown=onecube:onecube alembic.ini .
USER onecube
EXPOSE 8000
# No ejecutar migraciones automáticamente contra la base existente.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
