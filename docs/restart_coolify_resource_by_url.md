# Restarting a Coolify Resource by URL

How to find which Coolify instance and resource serves a public URL, and restart it with the Coolify CLI, using an Ansible playbook.

Given a public URL (e.g. `https://n8n-<service-uuid>.example.com/`), the playbook figures out which Coolify instance and which resource (application, service, or database) serves it, then restarts that resource via `coolify <type> restart <uuid>`. Use it instead of hunting through the Coolify dashboard when you only know the public hostname of the thing that needs a kick.

## Why this needs its own playbook

The setup this guide describes manages **two independent Coolify instances**, each with its own resource set. Restarting a resource requires running the CLI against the right one:

| Inventory group   | Host            | Coolify URL                          | Role               |
|-------------------|-----------------|--------------------------------------|--------------------|
| `coolify_servers` | `203.0.113.10`  | `https://main-coolify.example.com`   | Production         |
| `coolify_dev`     | `198.51.100.20` | `https://coolify.example.com`        | Dev / lower spec   |

There is no single API to query "which instance owns this URL". You have to list resources on both and match. The playbook automates that lookup instead of requiring the operator to already know (or guess) the host.

## How matching works

The playbook fetches `coolify app list`, `coolify service list`, and `coolify database list` (all `--format=json`) on **both** instances, then searches the full serialized JSON of every resource for the URL's hostname.

This is deliberately a substring search across the whole record rather than a lookup on a specific `domain`/`fqdn` field, because the Coolify CLI output does not expose one reliably:

- Standalone applications (`app list`) may or may not have a top-level `fqdn`-style field depending on build pack.
- **Docker-compose-based services** (verified against a live n8n service) have *no* top-level domain field at all in `service list --format=json`. The hostname only appears embedded inside the `docker_compose` text, as `SERVICE_URL_*`/`SERVICE_FQDN_*` env vars and Traefik/Caddy labels.

Searching the whole JSON blob (`target_hostname in (item | to_json)`) catches both cases with one code path.

The match is done at the *top-level resource* granularity. For a Coolify "service" bundle (e.g. n8n + n8n-worker + postgres + redis + task-runners running as one service), the playbook restarts the whole service by its service UUID, not an individual sub-application inside it, since `coolify service restart <uuid>` already restarts every container in the bundle.

## Usage

```bash
# Dry run (default) - just reports what would be restarted
ansible-playbook -i inventory.ini restart_coolify_resource_by_url.yml \
  -e 'target_url=https://n8n-<service-uuid>.example.com/'

# Actually restart it
ansible-playbook -i inventory.ini restart_coolify_resource_by_url.yml \
  -e 'target_url=https://n8n-<service-uuid>.example.com/' -e 'dry_run=false'
```

Behavior:

- **No match on either instance**: the play fails with a clear message.
- **Match on more than one resource** (ambiguous): the play fails rather than guessing; narrow the URL or restart manually by UUID.
- **Exactly one match**: restarts it on whichever host actually owns it, regardless of which inventory group that host belongs to.

## Known limitation: a disabled Coolify API

If the API is disabled on an instance (Settings, then API, in the Coolify dashboard), `coolify app list` fails with:

```text
Error: failed to list applications: failed to list applications: API error 403 on applications: API is disabled.
```

The playbook tolerates this gracefully (`ignore_errors: true` on the list tasks). A failed or empty list on one instance just means "0 matches there" and does not fail the whole run, so lookups still work as long as the resource lives on the instance where the API *is* enabled. But until the API is re-enabled, this playbook, and any other CLI-based automation (backups, audits of exited resources), cannot see or act on that instance's resources at all.

## Validated run

Ran end-to-end against a live dev instance for an n8n service URL:

1. Dry run correctly located the resource as `type=service uuid=<service-uuid> name=n8n-with-postgres-and-worker-<service-uuid>` on the dev host, with 0 (gracefully ignored) matches on the production host.
2. Real run (`dry_run=false`) issued `coolify service restart <service-uuid>`.
3. Polled `coolify service get <service-uuid> --format=json` every ~30s; status progressed `exited`, `starting:unhealthy`, `starting:unknown`, then `running:healthy` (all three sub-apps, `n8n`, `n8n-worker`, `task-runners`, healthy) in about 3.5 minutes.
4. Confirmed externally: `curl -o /dev/null -w '%{http_code}'` against the URL returned `200`.
