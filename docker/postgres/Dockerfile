# PostgreSQL's Debian packages support both amd64 and arm64.
FROM postgres:17-bookworm@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17-postgis-3 \
    && rm -rf /var/lib/apt/lists/*
COPY docker/postgres/init.sql /docker-entrypoint-initdb.d/10-watergeo.sql
