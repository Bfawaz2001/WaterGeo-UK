# PostgreSQL's Debian packages support both amd64 and arm64.
FROM postgres:17-bookworm@sha256:40865bc877a289da75963d97d72b59633f639fc5af7a4e856bfa3714cae5b536
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-17-postgis-3 \
    && rm -rf /var/lib/apt/lists/*
COPY docker/postgres/init.sql /docker-entrypoint-initdb.d/10-watergeo.sql
