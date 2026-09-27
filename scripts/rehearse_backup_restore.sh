#!/bin/sh
set -eu

if [ "${WATERGEO_DISPOSABLE_REHEARSAL:-}" != "1" ]; then
  echo "Refusing backup/restore: set WATERGEO_DISPOSABLE_REHEARSAL=1 for isolated rehearsal databases." >&2
  exit 2
fi

source_container=${WATERGEO_REHEARSAL_SOURCE_CONTAINER:-}
restore_container=${WATERGEO_REHEARSAL_RESTORE_CONTAINER:-}
case "$source_container:$restore_container" in
  watergeo-v1-rehearsal-*:watergeo-v1-rehearsal-*) ;;
  *) echo "Both container names must begin watergeo-v1-rehearsal-." >&2; exit 2 ;;
esac

artifact=${WATERGEO_REHEARSAL_BACKUP:-/tmp/watergeo-rehearsal.dump}
case "$artifact" in /tmp/watergeo-rehearsal-*.dump|/tmp/watergeo-rehearsal.dump) ;; *)
  echo "Backup artifact must be a /tmp/watergeo-rehearsal*.dump path." >&2; exit 2 ;;
esac
if [ -e "$artifact" ]; then
  echo "Refusing to overwrite existing backup artifact: $artifact" >&2
  exit 2
fi

signature_sql="SELECT count(*) || ':' || md5(string_agg(payload, '' ORDER BY payload)) FROM (
SELECT row_to_json(s)::text payload FROM watergeo.water_supply_snapshot s UNION ALL
SELECT row_to_json(s)::text FROM watergeo.hydrology_snapshot s UNION ALL
SELECT row_to_json(s)::text FROM watergeo.catchment_snapshot s UNION ALL
SELECT row_to_json(s)::text FROM watergeo.water_quality_snapshot s UNION ALL
SELECT row_to_json(s)::text FROM watergeo.stream_reservoir_snapshot s UNION ALL
SELECT row_to_json(s)::text FROM watergeo.thames_discharge_snapshot s) snapshots"
source_signature=$(docker exec "$source_container" psql -XAt -U postgres -d watergeo -c "$signature_sql")
case "$source_signature" in 0:*) echo "Source rehearsal database has no accepted snapshots." >&2; exit 1 ;; esac

started=$(date +%s)
docker exec "$source_container" pg_dump -Fc -U postgres -d watergeo > "$artifact"
backup_finished=$(date +%s)
docker exec -i "$restore_container" pg_restore --clean --if-exists --exit-on-error \
  -U postgres -d watergeo < "$artifact"
restore_finished=$(date +%s)

revision=$(docker exec "$restore_container" psql -XAt -U postgres -d watergeo \
  -c 'SELECT version_num FROM watergeo.alembic_version')
test "$revision" = "0011"
restore_signature=$(docker exec "$restore_container" psql -XAt -U postgres -d watergeo -c "$signature_sql")
test "$source_signature" = "$restore_signature"
bytes=$(wc -c < "$artifact" | tr -d ' ')
printf 'backup_bytes=%s backup_seconds=%s restore_seconds=%s revision=%s snapshot_signature=%s\n' \
  "$bytes" "$((backup_finished-started))" "$((restore_finished-backup_finished))" \
  "$revision" "$restore_signature"
