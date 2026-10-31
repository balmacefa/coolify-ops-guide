# Backup and Restore a Coolify Instance

A condensed runbook for backing up a Coolify instance and restoring it on a new server (database, `APP_KEY`, SSH keys).

> Based on the official Coolify documentation ("Backup and Restore Your Coolify Instance", coollabsio/coolify-docs). This is a paraphrased summary without the original screenshots; consult the upstream docs for the authoritative and current version.

This only backs up and restores the Coolify instance itself, **not your application data**. Dashboard settings are restored, but application data (volume mounts) must be backed up and restored separately (see `migrate-apps-different-host.md`).

There are two ways to create backups: S3-compatible storage (automatic; just download the file from your S3 provider) or a manual backup from the dashboard (covered below).

## 1. Create a manual backup

1. In the dashboard go to **Settings**, then the **Backup** tab.
2. Click **Backup Now**. It runs in the background.
3. When finished, use **Download** to save the file locally, or copy the shown path and move it to the new server with `scp`.

## 2. Retrieve your `APP_KEY`

The `APP_KEY` is needed to decrypt your data after restoring. Open the **Terminal** tab (server `localhost` by default) and run:

```sh
cat /data/coolify/source/.env
```

Copy the `APP_KEY` value and store it securely. Without it you cannot restore the backup.

## 3. Back up Coolify's SSH keys

Coolify generates SSH key files under `/data/coolify/ssh/keys`. They must come along so your managed servers stay reachable.

```sh
ls -l /data/coolify/ssh/keys
```

You will see files named `ssh_key@<random_id>` (ED25519 keys). Copy all of them to a secure place for later. Also take the corresponding public keys from the old server's `~/.ssh/authorized_keys` and **append** them to the new server's `~/.ssh/authorized_keys` (do not replace existing entries).

## 4. Prepare the new server

Install a fresh Coolify, pinning the **same version** as the old instance:

```sh
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash -s 4.0.0-beta.400
```

Replace `4.0.0-beta.400` with your version. A fresh install shows the registration page, which confirms no data exists yet.

## 5. Transfer and restore the backup

1. Copy the backup file and the SSH keys to the new server (scp, sftp, etc.).
2. Stop Coolify:

   ```sh
   docker stop coolify coolify-redis coolify-realtime coolify-proxy
   ```

3. Restore into the database container:

   ```sh
   cat /path/to/your_backup_file \
     | docker exec -i coolify-db \
       pg_restore --verbose --clean --no-acl --no-owner -U coolify -d coolify
   ```

   Warnings about existing foreign keys or sequences can usually be ignored if the base structure remains intact.

## 6. Replace the auto-generated SSH keys

```sh
rm -f /data/coolify/ssh/keys/*
```

Then move your old key files (from step 3) into `/data/coolify/ssh/keys/`.

## 7. Update environment settings

Edit `/data/coolify/source/.env` and add the old key as `APP_PREVIOUS_KEYS`. If you have migrated several times, list multiple keys separated by commas with no spaces:

```sh
# Single key
APP_PREVIOUS_KEYS=your_previous_app_key_here

# Multiple keys
APP_PREVIOUS_KEYS=app_key_1,app_key_2,app_key_3
```

## 8. Restart Coolify

Re-run the install script (same version) to apply the restored data and environment:

```sh
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash -s 4.0.0-beta.400
```

Then open the dashboard and log in with your previous credentials; projects, deployments and settings should be back.

## Troubleshooting

- **500 error on login or project access:** double-check that `APP_PREVIOUS_KEYS` is correctly set in `.env`.
- **Permission denied errors on directories:** Coolify runs as root, so set ownership accordingly:

  ```sh
  sudo chown -R root:root /data/coolify
  ```

- **Server is not reachable (permission denied over SSH):** Coolify cannot SSH into your servers because it does not have the same key files. Make sure you copied all of `/data/coolify/ssh/keys/` from the old host into the same path on the new host, with exactly the same files, and that the matching public keys are in the managed servers' `~/.ssh/authorized_keys`.
