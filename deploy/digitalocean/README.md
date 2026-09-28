# DigitalOcean deployment assets

These files define the reviewed first-preview topology. `app.yaml` is a template, not
a directly deployable or secret-bearing specification.

Render it to a new private file outside the repository:

```bash
set -a
source /secure/path/watergeo-production.env
set +a
uv run --locked watergeo-render-digitalocean-app --output /private/tmp/watergeo-app.yaml
uv run --locked watergeo-production-preflight --online --spec /private/tmp/watergeo-app.yaml
```

The default render keeps App Platform maintenance mode enabled. The initial bootstrap
is an explicit temporary POST_DEPLOY job:

```bash
uv run --locked watergeo-render-digitalocean-app \
  --include-bootstrap --output /private/tmp/watergeo-bootstrap-app.yaml
```

After the bootstrap succeeds, immediately update the app with a newly rendered normal
spec so later deployments run only the PRE_DEPLOY migration. Only after acceptance,
render another new file with `--public` to disable maintenance mode. Rendered files
contain encrypted-on-submission secret inputs: keep them outside Git, mode `0600`, and
delete them after App Platform accepts the spec.

The template has no recurring jobs. Phase 14 must not activate production schedules.
See [the full runbook](../../docs/deployment/digitalocean-preview.md).
