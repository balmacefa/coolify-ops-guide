# Keeping the Coolify proxy healthy after a reboot (stock apache2 vs Traefik)

A reboot can leave a stock `apache2` package holding port 80 so that Coolify's Traefik proxy fails to start; this guide explains the incident, why `mask` beats `disable`, and the idempotent check that fixes it.

## What the check does

An idempotent, dry-run-first health and self-heal routine for the Coolify Traefik proxy (`coolify-proxy` container), typically implemented as an Ansible playbook:

1. Check whether a stock `apache2` systemd service is present, active, and/or already `masked`.
2. Check whether the `coolify-proxy` Docker container is `running`.
3. In dry-run (the default), report the current state and change nothing.
4. In apply mode: `systemctl mask apache2` (stop + disable + mask; mask is the part that matters, see below) if it is present, `docker start coolify-proxy` if it is not running, then wait for ports 80 and 443 to be listening locally.

It is safe to re-run any time, including as a routine post-reboot check; every step is a no-op if the state is already correct.

## The incident

On 2026-09-22, a forced reboot of a production Coolify server (triggered by genuine resource exhaustion, see below) caused the Coolify dashboard and every other Coolify-hosted domain on that box to return a Cloudflare `502 Bad Gateway - Host Error`.

**Root cause:** the VPS shipped with a **stock Debian `apache2` package installed and `enabled`** at the systemd level, a leftover from the base VPS image, unrelated to and unused by the Coolify/Docker stack. It was never disabled after provisioning. On every boot, systemd starts `apache2` early and it binds port 80 before Docker/Traefik gets a chance to. That makes the `coolify-proxy` (Traefik `v3.7`) container fail to bind and exit (`Exited (255)`), leaving **nothing listening on 80/443 at all**. Hence Cloudflare's 502: it could not even establish a connection to the origin, so this was not a routing or auth error at Traefik.

Confirmed at the time: `systemctl show apache2 -p ActiveEnterTimestamp` showed apache2 started at the moment of the reboot. `apache2ctl -S` showed only the default `000-default.conf` vhost serving `/var/www/html`, with no real content, confirming it was just the untouched package default.

Immediate fix by hand: `systemctl stop apache2 && systemctl disable apache2`, then `docker start coolify-proxy`. That restored service, but `disable` alone only stops systemd's *automatic* boot-time start. It does not block a manual `systemctl start apache2` or a later `apt` upgrade/reinstall of the package re-enabling its unit file. The idempotent check exists to apply and enforce the stronger, permanent fix (`masked`) as a repeatable task rather than a one-off command that could silently regress.

## Why `masked`, not just `disabled`

`systemctl disable` only removes the service from being *auto-started* at boot targets; it can still be started manually (`systemctl start apache2`) or re-enabled by a package install/upgrade hook. `systemctl mask` replaces the unit file with a symlink to `/dev/null`, so **nothing** (not `systemctl start`, not a dependency pull-in, not a package postinst script) can start it until it is explicitly unmasked. Since apache2 serves no purpose on this host and the failure mode (silent 502 across every hosted domain) is severe, `masked` is the correct permanent state. In Ansible this is `ansible.builtin.systemd` with `masked: true`, which also handles `state: stopped` / `enabled: false` in the same idempotent task.

## Relationship to the resource-exhaustion incident

This is a *separate* issue from why the reboot happened in the first place. Right before the reboot, memory was at 97.69% and CPU load at 175% (against a 95% threshold); the box was genuinely resource-starved (SSH itself was timing out during the banner exchange because `sshd` could not fork in time). That triggered the forced reboot. The apache2/Traefik port conflict is a side effect that only surfaced *because* a reboot happened; it would recur on any future reboot (planned or crash-induced) until apache2 is masked. A reboot routine does not check for or fix this by itself, so run the proxy health check after any reboot of a Coolify host, or fold it into the reboot routine as a post-reboot step.

The actual driver of the resource exhaustion in that case was a `flowise` container crash-looping (88 restarts) on a permissions error (`EACCES: permission denied, mkdir '/home/node/.flowise/storage'`): its data volume was owned by `root:root` while the container runs as uid 1000, pegging a full CPU core. The container was stopped as a mitigation; the underlying fix is to `chown -R 1000:1000` the volume's `_data` directory under `/var/lib/docker/volumes/`. As of writing that had not been applied, a second, independent piece of unfinished work unrelated to the proxy/apache2 fix.

## Usage

Ansible example (dry run by default):

```bash
# Check current state without changing anything (default dry_run=true)
ansible-playbook -i inventory.ini ensure_coolify_proxy_healthy.yml

# Apply the fix (mask apache2 if present, start coolify-proxy if down)
ansible-playbook -i inventory.ini ensure_coolify_proxy_healthy.yml -e 'dry_run=false'
```

The equivalent manual steps:

```bash
systemctl mask --now apache2
docker start coolify-proxy
ss -ltn | grep -E ':(80|443)\b'
```
