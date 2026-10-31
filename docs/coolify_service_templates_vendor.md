# Vendoring Coolify Repos as Git Submodules

How to keep shallow, optionally sparse-checked-out git submodules of the upstream Coolify repos as a local, searchable reference (notably the one-click service template catalog).

`vendor/` holds shallow git submodules of forks of the upstream `coollabsio/coolify*` repos (`coolify`, `coolify-docs`, `coolify-cli`, `coolify-examples`), all pinned to branch `v4.x`. Forking (rather than pointing submodules straight at upstream) gives you push access if you ever need to patch a vendored file, and keeps local reference copies available even if upstream is unreachable. Replace the fork URLs below with your own.

## `vendor/coolify`

A local, searchable reference for what Coolify's one-click service catalog actually contains and how each template is defined. It is useful when a `coolify service create --list-types` result is missing something you expected (for example, a service such as Diun that has no one-click template at all).

Service template compose files live at `vendor/coolify/templates/compose/*.yaml`; the full catalog metadata is in `vendor/coolify/templates/service-templates.json`.

### Why sparse-checkout

`coollabsio/coolify` is the entire Coolify application (a large Laravel monorepo), not a templates-only repo. There is no dedicated templates repo upstream. To avoid pulling the whole app just for reference files, the submodule is both **shallow** (`--depth 1`, no history) and **sparse-checked-out** to only the `templates/` directory (~6MB instead of the full checkout).

Git does not persist sparse-checkout settings inside `.gitmodules` or the submodule's own tracked state. They live in the submodule's local `.git/info/sparse-checkout`, so **a fresh clone must redo the sparse-checkout setup once** after `git submodule update --init`:

```bash
git submodule update --init --depth 1 vendor/coolify
cd vendor/coolify
git sparse-checkout init --cone
git sparse-checkout set templates
cd ../..
```

### Updating

A small helper script (`update_vendor_coolify.sh` in the original setup) can handle the fresh-clone init and sparse-checkout setup automatically, fetch the latest commit on the tracked branch (`v4.x`), and do nothing if already up to date. Typical flags: no flag (fetch, checkout latest, commit locally if changed), `--no-commit` (fetch and checkout only), and `--push` (also commit and push the bump). It is safe to run repeatedly, e.g. from a cron entry. Equivalent manual steps:

```bash
cd vendor/coolify
git fetch --depth 1 origin v4.x
git checkout FETCH_HEAD
cd ../..
git add vendor/coolify
git commit -m "Update vendor/coolify templates snapshot"
```

## `vendor/coolify-docs`, `vendor/coolify-cli`, `vendor/coolify-examples`

Full (non-sparse) shallow checkouts of forks of `coolify-docs` (the documentation site source), `coolify-cli` (the standalone Coolify CLI source, useful for checking flag/behavior changes against what you install on your hosts), and `coolify-examples` (deployment/compose examples for various stacks). These are small enough that a full checkout is fine; no sparse-checkout needed.

## First-time setup after cloning

Git submodules are not populated by a plain `git clone`. After cloning:

```bash
git submodule update --init --depth 1 vendor/coolify-docs vendor/coolify-cli vendor/coolify-examples

# vendor/coolify additionally needs sparse-checkout redone (see above)
git submodule update --init --depth 1 vendor/coolify
cd vendor/coolify
git sparse-checkout init --cone
git sparse-checkout set templates
cd ../..
```

## Updating the other submodules

Same pattern as `vendor/coolify` above, e.g. for `vendor/coolify-docs`:

```bash
cd vendor/coolify-docs
git fetch --depth 1 origin v4.x
git checkout FETCH_HEAD
cd ../..
git add vendor/coolify-docs
git commit -m "Update vendor/coolify-docs snapshot"
```
