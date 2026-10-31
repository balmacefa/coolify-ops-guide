# Deploying GoatCounter as a Coolify One-Click Service

How to deploy GoatCounter (self-hosted web analytics) as a single-container Coolify one-click service with an Ansible playbook, applying the same domain-routing workarounds as the n8n guide.

[GoatCounter](https://www.goatcounter.com/) is a lightweight, privacy-friendly, self-hosted web analytics tool (a Google Analytics alternative). The playbook uses Coolify's `goatcounter` template (single container, no external database; see `templates/compose/goatcounter.yaml` in the Coolify repo) with a caller-selectable public domain, following an idempotent create-or-reuse pattern.

```bash
ansible-playbook -i inventory.ini deploy_goatcounter.yml \
  -e 'goatcounter_domain=https://goatcounter-public.example.com'
```

Deploy a second, independently-named/-routed instance:

```bash
ansible-playbook -i inventory.ini deploy_goatcounter.yml \
  -e 'goatcounter_service_name=goatcounter-internal' -e 'goatcounter_domain=https://goatcounter-internal.example.com'
```

## Why this needs the n8n-style domain-routing PATCH

The simpler pattern of pointing a domain at a service purely by updating its `SERVICE_URL_*`/`SERVICE_FQDN_*` env vars and restarting only works for services with no HTTP server at all (where the domain is cosmetic). GoatCounter, like n8n, **is** a real HTTP-serving web app (single container, port 8080, real dashboard/login UI), so it needs the same three coolify-cli/platform workarounds, written up in full (with the PHP source excerpts) in [deploy_n8n_service.md](deploy_n8n_service.md):

1. **The CLI's service-type allowlist may be stale.** `coolify service create --list-types` is a hardcoded client-side list, not fetched from the server. If it does not recognize `goatcounter`, the playbook checks whether the Coolify platform itself bundles the template server-side (`docker exec coolify test -f /var/www/html/templates/compose/goatcounter.yaml`) and, if so, falls back to a direct `POST /api/v1/services` call using the CLI's own already-authenticated token (`no_log: true` throughout).
2. **The CLI has no way to set a service's actual routing domain.** `coolify service env update <uuid> SERVICE_URL_GOATCOUNTER --value=...` only changes what GoatCounter itself thinks its base URL is. It does not touch the per-application `fqdn` that Coolify's Traefik-label generator reads from. The playbook sets that via `PATCH /api/v1/services/{uuid}` with a `urls: [{name: "goatcounter", url: "<domain>:8080"}]` body, same as n8n.
3. **The domain URL must include the backend port (`8080` for GoatCounter's template).** Coolify's label generator only emits the Traefik `service=`/`loadbalancer.server.port=` labels when a port is present in the domain URL string itself. Omit it and Traefik ends up with a router that matches the hostname but has no backing service: "no available server" even though the container is healthy. The playbook always suffixes `goatcounter_domain` with `goatcounter_container_port` (default `8080`) in the `urls` PATCH. This port never appears in what end users actually hit (Traefik's HTTPS entrypoint is always `:443`).

Unlike n8n (5 containers: main, worker, task-runners, Postgres, Redis), GoatCounter's template is a single container with no external database (state lives in a bind-mounted volume), so there is nothing else to poll for health beyond the one service. Otherwise the playbook is a direct adaptation of the n8n one.

## Cloudflare prerequisites (not managed by this playbook)

Same three requirements as the n8n deployment (see [deploy_n8n_service.md](deploy_n8n_service.md#cloudflare-prerequisites-not-managed-by-this-playbook) for the full explanation of why DNS alone is insufficient):

1. A DNS record for the hostname (proxied).
2. A dedicated Cloudflare Tunnel ingress rule mapping the exact hostname to the origin (`https://127.0.0.1:443`, `noTLSVerify: true`).
3. If relying on a `*.example.com` wildcard, be aware that it may round-robin between several Coolify hosts with no health checks. Prefer a dedicated CNAME straight to the host that actually runs this instance.

## First-run setup (not automated)

GoatCounter's own initial site/admin-account creation happens through its web UI on first visit (there is no CLI-scriptable equivalent bundled in this template). Complete that manually after the playbook confirms the service is `running:healthy`.

## Note

The three coolify-cli/platform gaps this playbook works around were originally discovered and debugged while deploying n8n; this document intentionally does not repeat the full source-code investigation (see [deploy_n8n_service.md](deploy_n8n_service.md)). This playbook has not yet been run end-to-end against a live production instance (unlike the n8n one, which has a documented validated run). Run it and record the result before relying on it unattended.
