# Migrate Applications to Another Coolify Host

A condensed runbook for moving an app's data (bind mounts and Docker volumes) from one Coolify server to another.

> Based on the official Coolify documentation ("Migrate Applications", coollabsio/coolify-docs). This is a paraphrased summary: the long interactive helper scripts and screenshots from the original are not reproduced here; consult the upstream docs for them.

Coolify has no built-in way to migrate an application between servers. You deploy the app manually on the new server (Coolify already installed there) and copy its databases and volumes across.

## 1. Understand where data lives

- **Bind mounts:** a host directory or file is mapped into the container. Back up by copying the host path to the new server and updating the bind-mount path in the app's configuration.
- **Volume mounts:** a Docker volume (usually created by Coolify) stored under `/var/lib/docker/volumes/<VOLUME_NAME>`. Do not copy that directory directly; use the Docker-recommended backup and restore through a temporary container.

Bind mounts are simple, so the rest of this guide focuses on volumes.

## 2. Overview of the volume process

Following [Docker's guidance for backing up, restoring or migrating volumes](https://docs.docker.com/engine/storage/volumes/#back-up-restore-or-migrate-data-volumes):

1. Mount the volume into a temporary container.
2. Archive its contents into a tarball.
3. Copy the tarball to the host and remove the temporary container.
4. Transfer the tarball to the new server.
5. Create a fresh volume on the destination.
6. Mount the tarball into a temporary container.
7. Extract the archive into the new volume.

## 3. Back up the volume (old server)

Find the volume name with `docker volume ls` or on the app's **Persistent Storage** page in Coolify. **Stop the application** first so the backup is consistent. Then:

```sh
VOLUME_NAME=<volume name>
BACKUP_DIR=./volume-backup
mkdir -p "$BACKUP_DIR"

docker volume ls --quiet | grep -qx "$VOLUME_NAME" || { echo "Volume not found"; exit 1; }

docker run --rm \
  -v "$VOLUME_NAME":/volume \
  -v "$(pwd)/$BACKUP_DIR":/backup \
  busybox \
  tar czf /backup/"$VOLUME_NAME"-backup.tar.gz -C /volume .
```

Verify that `volume-backup/<VOLUME_NAME>-backup.tar.gz` exists.

## 4. Transfer the backup to the new server

Use any secure method. For example with `scp` (SSH key authentication preferred):

```sh
ssh -p 22 root@203.0.113.10 "mkdir -p /root/backups/volume-backup"
scp -P 22 -r ./volume-backup/. root@203.0.113.10:/root/backups/volume-backup
```

Adjust the user, address, port, key and destination path for your new server.

## 5. Restore on the new server

The upstream example uses Umami Analytics (PostgreSQL); adjust paths and volume names for your own database.

1. Deploy the application on the new server with Coolify, then **stop it** so its volumes exist but are not in use.
2. Make sure the target volume exists (`docker volume ls`); create it with `docker volume create <name>` only if it does not. Double-check the name so you do not restore into the wrong volume.
3. Make sure no container is using the target volume, then restore:

   ```sh
   TARGET_VOLUME=<volume name>
   BACKUP_DIR=/root/backups/volume-backup
   BACKUP_FILE=<volume name>-backup.tar.gz

   docker run --rm \
     -v "$TARGET_VOLUME":/volume \
     -v "$BACKUP_DIR":/backup \
     busybox \
     sh -c "cd /volume && tar xzf /backup/$BACKUP_FILE"
   ```

## 6. Start the application

In the Coolify dashboard click **Deploy**. The app should now use the migrated data. If it does not, or the logs show errors, repeat the restore step to make sure all files were copied correctly.

If the database credentials (username, database name or password) differ on the new server, update them in Coolify's dashboard to match those of the old server.
