# Troubleshooting: Coolify behind a Cloudflare-Tunnel-only firewall

Fixes for redirect loops, WebSocket failures and "works locally, not from the internet" problems when Coolify's web ports are reachable only through a Cloudflare Tunnel.

## Context

Once a host is locked down so that Coolify's web ports are **only** reachable through a Cloudflare Tunnel (`cloudflared` dialing `127.0.0.1` locally), there is no direct origin access to fall back on. That changes how a few things fail. Before changing anything, gather the data each section below refers to: local HTTP/HTTPS routing checks, a WebSocket check, and tunnel and firewall state.

## "ERR_TOO_MANY_REDIRECTS" / infinite redirect loop on the public hostname

**Symptom:** the browser loops between the hostname and itself; `curl -L` never terminates (or times out after many hops).

**Cause:** the tunnel ingress rule for the hostname points at Traefik's **plain-HTTP entrypoint** (`http://127.0.0.1:80`) instead of its HTTPS one. Traefik unconditionally redirects HTTP to HTTPS at that entrypoint regardless of `X-Forwarded-Proto` (confirmed empirically: setting that header on a direct request made no difference). Every request becomes:
`Cloudflare (https) -> tunnel -> :80 -> 302 to https:// -> Cloudflare -> tunnel -> :80 -> ...` forever, since the tunnel's `service:` is fixed at plain HTTP.

**Fix:** point the tunnel ingress `service` at Traefik's HTTPS entrypoint: `https://127.0.0.1:443` with `originRequest.noTLSVerify: true`. Traefik presents its self-signed default certificate internally, which is fine: Cloudflare already terminates the real, publicly trusted TLS at its edge, and the tunnel leg is a private loopback-only hop. The tunnel configuration can be updated through the Cloudflare API (`PUT /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations`) or the dashboard.

**Verify:** a local HTTPS request through Traefik should return a real app response (for example `403`/`200` at `/login`), not a redirect loop. A local HTTP request on port 80 is *expected* to show `302 -> https://...`; that is Traefik's normal behavior. The bug was only in pointing the tunnel *at* that port.

## WebSocket 502 / realtime features (live logs, live status) not working

**Symptom:** the dashboard loads and works, but deployment logs and status do not update live; the browser console shows WebSocket connection failures.

**Cause 1 - no route at all:** Coolify's frontend builds its WebSocket URL from the `PUSHER_HOST`/`PUSHER_PORT` env vars (see `getRealtime()` in `bootstrap/helpers/shared.php` and the Echo config in `resources/views/layouts/base.blade.php` in Coolify's source), falling back to the page's own hostname plus port `6001` if unset. That fallback port is not reachable once direct origin access is closed, and Cloudflare's DNS proxy does not forward ports 6001/6002 anyway (only a fixed set of ports; see [Cloudflare's supported ports list](https://developers.cloudflare.com/fundamentals/reference/network-ports/)).

**Fix:** give realtime (Soketi) its own tunnel-routed hostname on port 443 (for example `realtime.example.com`) and set `PUSHER_HOST`/`PUSHER_PORT` in Coolify's `.env` to match, then reload Coolify.

**Cause 2 - `read: connection reset by peer` on `[::1]:6001`:** even with a correct tunnel ingress rule, `cloudflared`'s logs (`journalctl -u cloudflared`) showed it dialing the IPv6 loopback (`::1`) for a `service: http://localhost:6001` rule and getting the connection reset, while the exact same request worked locally via `curl`. `localhost` resolves to both `::1` and `127.0.0.1`, and something in the docker-proxy/Soketi (uWebSockets) path did not like the IPv6 leg specifically.

**Fix:** use `http://127.0.0.1:6001` (and `https://127.0.0.1:443` for the main app) in tunnel ingress rules. Always prefer the literal IPv4 loopback address over `localhost` for tunnel `service:` targets.

**Verify:** a WebSocket upgrade request should return `101`. Read the live `PUSHER_APP_KEY` from `.env` and request `/app/{key}?protocol=7`. A bare `/` on Soketi returns `200`, not `101`; do not test the wrong path.

## Everything works over SSH/locally but not from the internet at all

**Symptom:** `curl` from the host itself works; `curl` from your own machine times out or is refused, even on a hostname that should be routed through the tunnel.

**Checklist:**

1. Is the tunnel healthy? Check via the Cloudflare API or dashboard (`status: healthy`, recent `conns_active_at`); this is not visible from the host itself.
2. Does the DNS record exist, is it proxied (orange cloud), and is it a CNAME to `<tunnel-id>.cfargotunnel.com`?
3. Does an ingress rule exist for that exact hostname in the tunnel's config, and is it not shadowed by an earlier rule? Tunnel ingress is evaluated top to bottom, first match wins, so order matters.
4. **Do not forget IPv6.** A firewall lockdown must cover both the `iptables` and `ip6tables` `DOCKER-USER` chains. If you are hand-checking firewall state, checking only `iptables -S DOCKER-USER` on a host with a routable global IPv6 address (`ip -6 addr show <interface>`) will make a locked-down host look secure while it is fully open on v6. This was a real gap found and fixed on 2026-08-10: the original firewall automation only covered IPv4 for several hours before the gap was caught while debugging an unrelated WebSocket issue.
