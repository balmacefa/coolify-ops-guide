# Deploying n8n as a Coolify One-Click Service

How to deploy n8n (queue mode) as a Coolify one-click service with an Ansible playbook, and the three CLI/platform gaps you must work around to get a custom public domain actually routed.

The playbook deploys n8n (workflow automation) using the `n8n-with-postgres-and-worker` template (main + worker + Postgres + Redis + task-runners, queue mode), with a caller-selectable public domain, following an idempotent create-or-reuse pattern.

```bash
ansible-playbook -i inventory.ini deploy_n8n.yml \
  -e 'n8n_domain=https://n8n-public.example.com'
```

Deploy a second, independently-named/-routed instance:

```bash
ansible-playbook -i inventory.ini deploy_n8n.yml \
  -e 'n8n_service_name=n8n-internal' -e 'n8n_domain=https://n8n-internal.example.com'
```

## Why this needs more than the simple env-var pattern

A simpler pattern points a domain at a service purely by updating its `SERVICE_URL_*`/`SERVICE_FQDN_*` env vars, then restarting. That pattern **does not work** for getting a public domain actually routable through Traefik. It only appears to work for services with no HTTP server at all (where the domain is cosmetic).

Getting `https://n8n-public.example.com` to actually return the n8n UI (not "no available server") surfaced three real, undocumented gaps between the `coolify` CLI (1.6.2) and the Coolify platform (4.1.2). They were found by reading Coolify's own PHP source directly inside the `coolify` container on the host (`docker exec coolify sh -c '...'` against `app/Http/Controllers/Api/ServicesController.php` and `bootstrap/helpers/docker.php`). None of this is in the CLI's `--help` output or the public API docs.

### 1. The CLI's service-type allowlist is stale

`coolify service create --list-types` is a **hardcoded list baked into the CLI binary** (`validServiceTypes` in `coolify-cli/cmd/service/create.go`), not fetched from the server. As of CLI 1.6.2 it only knows `n8n` and `n8n-with-postgresql`, not `n8n-with-postgres-and-worker`, even though the Coolify *platform* (4.1.2) already bundles that template server-side (`/var/www/html/templates/compose/n8n-with-postgres-and-worker.yaml` inside the `coolify` container). The CLI rejects the type before ever hitting the API.

**Fix:** when the CLI allowlist rejects the type but the bundled template file exists on the server, the playbook creates the service with a direct `POST /api/v1/services` call instead. It uses the same JSON shape the CLI itself sends (`type`, `server_uuid`, `project_uuid`, `environment_name`, `name`, `instant_deploy`), just bypassing the client-side gate. The token is read from the CLI's own already-authenticated local config (`~/.config/coolify/config.json` on the host) and never logged (`no_log: true` throughout).

### 2. The CLI has no way to set a service's actual routing domain

`coolify service env update <uuid> SERVICE_URL_N8N --value=...` only changes what **n8n itself thinks its base URL is** (it feeds `N8N_EDITOR_BASE_URL`/`WEBHOOK_URL`/`N8N_HOST`). It does **not** touch the per-application `fqdn` column that Coolify's Traefik-label generator reads from. The public hostname keeps returning "no available server" (routed to the auto-generated `*.sslip.io` domain) no matter how many times you restart.

The only way to set that `fqdn` is `PATCH /api/v1/services/{uuid}` with a body like:

```json
{"urls": [{"name": "n8n", "url": "https://n8n-public.example.com:5678"}],
 "force_domain_override": true, "instant_deploy": true}
```

(`ServicesController::update_by_uuid` calls `applyServiceUrls`, which does `$application->fqdn = $containerUrls; $application->save();` per named sub-container.) `name` here is the **docker-compose service key** (`n8n`), not the overall Coolify service's display name. Those can differ if you override `n8n_service_name`.

**Fix:** the playbook does this PATCH directly (again via the CLI's own token, `no_log: true`), with `instant_deploy: true` in the same request so the container is recreated with fresh labels immediately. The env var step is *also* still needed, because it is what makes n8n's own UI/webhooks report the correct URL. Both happen; neither alone is sufficient.

### 3. The domain URL must include the backend port, or Traefik gets an empty router

This one cost the most debugging time because every other signal looked fine: containers healthy, on the right docker network, directly reachable (`docker exec coolify-proxy wget http://n8n-<uuid>:5678/healthz` succeeded), DNS resolving, tunnel ingress correct. Yet Traefik kept returning `no available server`.

Reading `bootstrap/helpers/docker.php`'s label-generation function found it:

```php
$port = $url->getPort();
...
if ($port) {
    $labels->push("traefik.http.routers.{$https_label}.service={$https_label}");
    $labels->push("traefik.http.services.{$https_label}.loadbalancer.server.port=$port");
}
```

`$port` is parsed **out of the domain URL string itself**. There is no separate "backend port" field anywhere in the `urls` PATCH. Coolify's own auto-generated domain (`http://n8n-<uuid>.<host-ip>.sslip.io:5678`) embeds the port for exactly this reason. Pass a plain `https://your-domain.com` (no port) and `$port` is null, the `if ($port)` block never runs, and you get a router with **no backing service at all**. Traefik matches the `Host()` rule, finds no service to forward to, and returns `no available server`, even though the container is perfectly healthy.

**Fix:** the playbook's `urls` PATCH always suffixes the domain with `n8n_container_port` (default `5678`, the template's fixed n8n port): `"{{ n8n_domain }}:{{ n8n_container_port }}"`. This port never appears in what end users actually hit. Traefik's HTTPS entrypoint is always `:443`; the suffix is purely label-generation metadata Coolify reads once at deploy time.

## Cloudflare prerequisites (not managed by this playbook)

In this setup Cloudflare changes are made through the API directly, not Ansible. Three things must exist for `n8n_domain`'s hostname before traffic actually reaches the deployed service. DNS resolving is **not enough by itself**:

1. A DNS record for the hostname (proxied, i.e. orange-cloud). A `*.example.com` wildcard covers any name under the zone, but see point 3 for why you likely want a dedicated record anyway.
2. **A dedicated tunnel ingress rule** (`cfd_tunnel/{id}/configurations`) mapping the exact hostname to the origin, e.g. `https://127.0.0.1:443` with `noTLSVerify: true`, in the same shape as the existing entry for the Coolify dashboard. Without this, Let's Encrypt's HTTP-01 challenge 404s and (depending on which record is actually authoritative for the hostname) requests may bypass the tunnel entirely.
3. If relying on a wildcard record specifically: when it round-robins between **multiple** Coolify hosts with no health checks, a request landing on a host that does not have the service deployed will fail. Use a **dedicated CNAME** straight to the tunnel of the host that actually runs the service instead of the wildcard.

## Validated run

Ran end-to-end against a live production instance:

1. Created the service via the API fallback (gap 1). The CLI allowlist rejected `n8n-with-postgres-and-worker`; the bundled template check passed.
2. Set `SERVICE_URL_*`/`SERVICE_FQDN_*` env vars and the `urls` PATCH (gaps 2 and 3) to `https://n8n-public.example.com:5678`.
3. Added the dedicated `n8n-public.example.com` CNAME and tunnel ingress rule (Cloudflare API, not this playbook).
4. Polled `coolify service get <uuid> --format=json` until all five containers (`n8n`, `n8n-worker`, `task-runners`, `postgresql`, `redis`) reported `running:healthy`.
5. Confirmed externally: `curl -o /dev/null -w '%{http_code}'` against `https://n8n-public.example.com/` returned `200`.
6. Re-ran the full playbook a second time (idempotency check). It correctly detected the existing service, skipped creation, re-applied env vars and the `urls` PATCH, redeployed cleanly, and was still `running:healthy` and `200` afterward.

## Note on API tokens and teams

Coolify API tokens are scoped to a **team**. A token from one team only sees that team's projects and servers, with different UUIDs than another team's. If a playbook's defaults point at one team's project/server UUIDs, deploying with a token from a different team requires passing explicit `-e` overrides for those UUIDs. If everything should live under one team, switch teams in the dashboard and regenerate the token; that is a manual step, not something fixable from the CLI/API alone.
