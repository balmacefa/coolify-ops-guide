# Traefik Version Upgrades

How to bump the Traefik image version on a Coolify proxy, plus two operational lessons from a first real upgrade (2026-08-16) that apply well beyond Traefik.

## Procedure

An upgrade playbook (or the equivalent manual steps) should:

1. Back up `docker-compose.yml` first.
2. Patch the `image: 'traefik:vX.Y'` line.
3. Validate with `docker compose config -q`.
4. Run `docker compose pull`. This is required: the image tag is a floating minor version like `v3.6`/`v3.7`, so a bare `docker compose up -d` will not fetch a newer patch under an already-pulled tag.
5. Recreate the container and wait for it to become healthy.
6. Report the actual running version via `docker exec coolify-proxy traefik version`.

Example invocations of such a playbook (dry run by default):

```bash
# Preview (default dry_run=true)
ansible-playbook -i inventory.ini upgrade_traefik_version.yml

# Apply for real
ansible-playbook -i inventory.ini upgrade_traefik_version.yml -e 'dry_run=false'

# Target a specific version (here the default was "v3.7")
ansible-playbook -i inventory.ini upgrade_traefik_version.yml -e 'dry_run=false' -e 'target_version=v3.6'
```

**Before bumping a minor version**, check `doc.traefik.io/traefik/v{N}/migrate/v3/` for breaking changes relevant to your proxy's actual config (Docker provider, file provider, any `experimental.plugins` setup, HTTP/3). The `v3.6` to `v3.7` upgrade was checked this way and found clean: its breaking changes were all Kubernetes CRD / Gateway API / `Host(*)` wildcard / BasicAuth-StripPrefix, none of which that proxy used.

## Lesson 1: a "Docker-healthy" container can still be unreachable through Traefik

During the `v3.7` upgrade, an n8n domain (`n8n.example.com` here) started timing out. The isolation steps that found the cause are a reusable checklist for "something's down after a proxy change":

1. **Test HTTP (port 80) and HTTPS (port 443) separately, on the host, bypassing Cloudflare**: `curl -H 'Host: <domain>' http://127.0.0.1/` and `curl -sk -H 'Host: <domain>' https://127.0.0.1/`. If one entrypoint works and the other does not, the problem is specific to whatever differs between them (for example an entrypoint-default middleware attached to only one).
2. **Compare against a second, known-different app on the same proxy** (ideally one defined differently, such as via the file provider vs. Docker labels) to tell "this one router is broken" from "the whole proxy is broken".
3. **Check `docker logs coolify-proxy` for the specific router name** (`grep <resource-name>`). Traefik logs router-build errors (bad middleware references, etc.) distinctly from ACME/cert errors, which are usually a separate, often pre-existing issue. There is usually some ACME noise in these logs; do not assume it is your bug.
4. If none of that explains it and the container reports `healthy`: **the container's Docker healthcheck passing does not mean Traefik can actually route to it.** This was hit twice in one session with n8n: a plain `docker compose up -d` (run directly against `/data/coolify/services/<uuid>/docker-compose.yml` after hand-editing a label) left the `n8n` container Docker-healthy but genuinely unreachable through Traefik (confirmed via host-local `curl`, bypassing Cloudflare: a real connection timeout, not an app-level 5xx). Both times the fix was **`coolify service restart <uuid>`**, not another `docker compose up -d`. The root cause of *why* the raw recreate leaves it unreachable was never identified; treat this as an empirical rule, not a fully understood one.

**Practical takeaway:** when recreating an n8n (or any Coolify-managed service) container after editing its compose file directly, prefer `coolify service restart <uuid>` over `docker compose up -d` in that resource's directory. If you must use `docker compose up -d` (for example with no Coolify CLI access), verify with a host-local `curl` that bypasses Cloudflare, not just `docker ps` / healthcheck status.

## Lesson 2: Traefik entrypoint-default middlewares do not merge with a router's own middleware list

This is what the `v3.7` smoke-test outage was actually about. If you attach something proxy-wide via `--entrypoints.https.http.middlewares=...`, any router that already declares its own `middlewares=` (Coolify adds a `gzip` compression middleware to most apps and services) silently never receives it: no error, it just does not apply. Check for that per resource before assuming an entrypoint default reaches everything. (This is why a global script-injection experiment done through a Traefik plugin was abandoned in favor of doing the injection at the Cloudflare edge with a Worker.)
