# Full Traefik Proxy Backup / Git-Tracked Mirror

Mirror the entire live Coolify Traefik proxy directory into a local, git-trackable folder to get diffable history of proxy config changes, while keeping `acme.json` out of git.

## What it is

A backup routine (implemented as an Ansible playbook) that mirrors the entire live Traefik proxy state from the Coolify server into a local directory, for diffable history of proxy config changes over time rather than a point-in-time archive.

```bash
ansible-playbook -i inventory.ini backup_traefik_proxy_full.yml
```

There is no `dry_run` gate: it is read-only against the remote host and all writes are local. Output lands at a **stable path** (for example `proxy_full_backups/live/`) that is **overwritten in place every run**, not timestamped, specifically so `git diff` / `git log` on that directory show real history instead of an ever-growing pile of snapshots. The directory is wiped and recreated each run so a file deleted on the remote host shows up as a deletion locally too.

Contents: `docker-compose.yml`, `dynamic/*.yaml`, `backups/*` (prior compose backups), and `acme.json`.

## Why `acme.json` is extracted but not tracked

`acme.json` holds the Let's Encrypt account key and every domain's private key. It is written to disk like everything else (so a local backup/restore is still possible) but is excluded from git via `.gitignore` (for example `proxy_full_backups/live/acme.json`). **This was a deliberate decision, not an oversight**: `git add`-ing it would put private keys into git history *permanently*, recoverable from old commits even after later deletion, which is a fundamentally different (and worse) exposure than a plaintext file on local disk. Everything else in the directory is meant to be committed.

Mid-session on 2026-08-16, `acme.json` was found already `git add`-staged from an earlier run's leftover output, most likely because the IDE's Source Control panel auto-staged it on file change. It was unstaged with `git restore --staged` and confirmed (`git log --all --diff-filter=A --name-only`) to have never been committed. **If your editor auto-stages changed files, double-check `git status` before committing after a backup run**, in case a stray `acme.json` gets picked up anyway (for example if the `.gitignore` rule is ever edited or removed).

## Design history

The routine went through three iterations before landing here: originally two separate playbooks, zip-wrapped, encrypted by default and timestamped. It is now one playbook, no zip, no encryption by default, one stable path.
