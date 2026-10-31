# Exporting a Combined Coolify Services Inventory to CSV

How an Ansible playbook builds one combined CSV of every application, service, and database across multiple Coolify instances, plus a security finding: the Coolify CLI leaks some secrets even without `--show-sensitive`.

The playbook (with a Jinja2 CSV template) lists every resource across **both** Coolify instances (`coolify_servers`/prod, `203.0.113.10`, and `coolify_dev`/dev, `198.51.100.20`) and writes one combined, human-readable CSV to `archive/services_inventory/<timestamp>_services_inventory.csv`.

Unlike the usual dump-to-disk pattern (encrypt, then delete the plaintext), this output **can be committed to git, unencrypted, and is not deleted after the run**. The row schema is built by hand from a fixed set of named fields (never a raw resource dump), so no credential can leak into it by accident.

## Usage

```bash
ansible-playbook -i inventory.ini export_services_inventory_csv.yml
```

The playbook is read-only against Coolify (`list`-only CLI calls, `ignore_errors: true` per call so an outage on one instance, such as a disabled API, still produces a partial inventory from the other). Live-validated on a real setup with 63 resources (24 apps / 33 services / 2 databases on dev, 0 apps / 3 services / 1 database on prod).

## CSV columns

```
instance,resource_type,name,uuid,status,engine,fqdn,git_repository,git_branch
```

- `instance`: `prod` or `dev`, derived from which inventory group the host is in.
- `resource_type`: `application` / `service` / `database`.
- `engine`: database engine (`postgresql`, `clickhouse`, ...) from the `type` field; blank for apps/services (not a meaningful concept there, since a Coolify "service" already bundles multiple engines).
- `fqdn`: see below.
- `git_repository`/`git_branch`: only ever populated for applications (the only resource type the CLI associates with a git ref).

### Why these columns and not others

The first version of the playbook shipped `project_uuid`, `environment_name`, `server_uuid`, `created_at`, `updated_at`, all permanently blank. This was verified empirically, not assumed: the full JSON key set of `coolify app/service/database list --format=json` **and** the equivalent `get --format=json` for one resource of each type were dumped against live data, and the union of keys across all 24 apps (mixed `dockerfile`/`dockercompose` build packs) was diffed to rule out a build-pack-specific gap. None of those five fields exist anywhere in Coolify CLI `1.7.0`'s JSON output, for any resource type, via `list` or `get`. They were dropped rather than left as permanently-empty columns, and replaced with `git_repository`/`git_branch` and a hardened `fqdn` (below), fields the CLI actually returns.

### `fqdn` extraction

Non-compose applications have a clean top-level `fqdn` field (stripped of its `https://` prefix here). Everything else, meaning every `dockercompose`-build-pack app and **every** service (`service list` has no `fqdn`-shaped field at all; its top-level keys are just `applications, databases, description, docker_compose, docker_compose_raw, name, status, uuid`), has to fall back to a regex search over the whole serialized record for a `SERVICE_FQDN_[A-Za-z0-9_]+` or `COOLIFY_FQDN` env var embedded in the `docker_compose` text. This is the same pragmatic "serialize and substring-search" approach used for restarting a resource by URL (`target_hostname in (item | to_json)`), just run in the opposite direction: extracting a hostname instead of matching a known one. Result: 100% `fqdn` coverage across all 57 apps and services in the live run. Databases stay correctly blank, because Coolify has no FQDN/domain concept for a database resource.

Implementation detail: Ansible's `regex_search(pattern, '\1')` filter returns a **list** (`["value"]`) on a match and `None` on no match, not a bare string (confirmed with a scratch playbook before relying on it). The row-building expression is `... | default([''], true) | first` specifically because of that list-wrapping, not because the match could itself be a list of multiple values.

## Security finding: Coolify CLI leaks secrets outside `--show-sensitive`

While diffing the JSON schemas above, it turned out that **without** `--show-sensitive`:

- `coolify database list`/`database get --format=json` return the database's **plaintext `postgres_password`**.
- `coolify app list`/`app get --format=json` return plaintext `manual_webhook_secret_{github,gitlab,bitbucket,gitea}`.

Confirmed against a live instance with CLI `1.7.0`. Neither secret is ever read by the playbook's row-building tasks (only `name`/`uuid`/`status`/`type` are pulled from database records; only `name`/`uuid`/`status`/`fqdn`/`git_repository`/`git_branch` from application records), but the **raw command stdout** would otherwise still hit Ansible's own task output and registered-variable state. The `Fetch application list` and `Fetch database list` tasks (and the `Parse resource lists` task that reads their `.stdout`) are marked `no_log: true` for exactly this reason. Copy that pattern into any playbook that runs `app list`/`app get`/`database list`/`database get`, even read-only ones, regardless of which fields it actually consumes.

## Known bug fixed along the way

The CSV-export play originally used `inventory_dir` to locate the output path. That play targets `hosts: localhost`, and `localhost` is not declared in `inventory.ini` (Ansible adds it implicitly), so `inventory_dir` came back undefined:

```text
fatal: [localhost]: FAILED! => {"msg": "The task includes an option with an undefined
variable. The error was: {{ inventory_dir }}/archive/services_inventory: 'inventory_dir'
is undefined. ..."}
```

Fixed by switching to `playbook_dir` (always defined, regardless of inventory host status) plus a relative `../..` back to the repo root. With the playbook living in `playbooks/system`, `playbook_dir + '/../../archive/services_inventory'` resolves the same as `inventory_dir + '/archive/services_inventory'` would have in a fixed repo layout.
