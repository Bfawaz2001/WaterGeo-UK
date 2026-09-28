# PostgreSQL's Debian packages support both amd64 and arm64.
FROM postgres:18-bookworm@sha256:3725f4e2499eef5134592b3b4ab79a543ed7f8e533b05b5b637af926630f6650
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17-postgis-3 \
    && rm -rf /var/lib/apt/lists/*
COPY docker/postgres/init.sql /docker-entrypoint-initdb.d/10-watergeo.sql
