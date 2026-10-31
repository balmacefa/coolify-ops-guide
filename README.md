# Coolify Ops Guide

Field-tested operations notes for running self-hosted [Coolify](https://coolify.io/): Traefik upgrades and backups, Cloudflare in front of Coolify, full-state backups, moving apps between hosts, one-click services (n8n, GoatCounter) and post-incident write-ups.

Distilled from a real production setup managed with Ansible. All domains, IPs and IDs are replaced with placeholders (`example.com`, `203.0.113.x`).

- Read it: https://balmacefa.github.io/coolify-ops-guide/
- Docs live in [`docs/`](docs/). Build the site with `pip install markdown && python scripts/build_site.py`.

Unofficial and not affiliated with Coolify. Contributions welcome (see [CONTRIBUTING.md](CONTRIBUTING.md)). MIT licensed.
