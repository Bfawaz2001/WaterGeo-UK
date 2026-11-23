# PostgreSQL's Debian packages support both amd64 and arm64.
FROM postgres:19-bookworm@sha256:f4859caf96de494e38efa69ed703b08a5bbd9605e152e604f2daec8841c87c41
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17-postgis-3 \
    && rm -rf /var/lib/apt/lists/*
COPY docker/postgres/init.sql /docker-entrypoint-initdb.d/10-watergeo.sql
