# Deployment and operations

## LAN

For a server at 192.168.10.20 (replace with your actual address), set:

~~~dotenv
NELSON_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.10.20
NELSON_COOKIE_SECURE=false
~~~

~~~bash
python -m app.cli run --host 0.0.0.0 --port 8000
~~~

Docker also needs NELSON_BIND_ADDRESS=0.0.0.0 and recreated containers. Allow TCP 8000 only from authorised LAN addresses. Users visit http://192.168.10.20:8000. Use HTTPS on networks where you do not trust every device.

## HTTPS with Caddy installed on the host

1. Point your domain's DNS to the server.
2. Keep the application bound to 127.0.0.1:8000.
3. Copy deploy/Caddyfile into the Caddy configuration and replace ai.example.com.
4. Set NELSON_ALLOWED_HOSTS=localhost,127.0.0.1,ai.example.com.
5. Set NELSON_COOKIE_SECURE=true.
6. Restart the app and reload Caddy.

Caddy forwards streaming without buffering. Uvicorn trusts forwarded headers from localhost by default. For a containerised proxy, configure its network and trusted forwarded IPs explicitly; never blindly trust arbitrary public headers.

Origin validation compares the browser origin to the effective application URL. Wrong proxy scheme forwarding can reject login/uploads. Correct the proxy instead of disabling validation.

The example uses a 21 GB limit for `/api/models/import`, 2,100 MB for `/api/migration/stage`, and 26 MB for ordinary uploads. The application enforces its own configured limits and requires administrator authentication for model import and migration. Public widget requests are anonymous only when publication is explicitly enabled. Change proxy/application limits together. Ensure the model directory is writable by the app account (container UID 10001) before using browser import.

## systemd

Example units assume a dedicated nelsonict account, project /opt/nelsonict-ai, virtual environment /opt/nelsonict-ai/.venv, and .env in that project. Create the account/environment and grant appropriate data/model permissions before installing units. Adjust paths for your server.

~~~bash
sudo cp deploy/nelsonict-ai.service deploy/nelsonict-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nelsonict-ai nelsonict-worker
sudo journalctl -u nelsonict-ai -u nelsonict-worker -f
~~~

Keep models read-only to ordinary web users. Configure MemoryMax for the worker based on available RAM.

## Docker resource limits

An example override:

~~~yaml
services:
  worker:
    mem_limit: 4g
    cpus: 2
~~~

API memory must cover GGUF weights, context cache, uploads, and optional query embeddings. If one PDF repeatedly crashes processing, remove it and prepare a smaller version.

## Guided migration and effective configuration

For the browser restore workflow, follow [the version 1.2 migration guide](UPGRADE-1.2.md#6-guided-backup-and-migration). It restores to a separate directory and writes `runtime-settings.json` at the original bootstrap data root. Restart both API and worker to read it. Keep that root accessible after migration; backing up SQLite does not include this external overlay.

The managed CLI uses reviewed native listen settings unless explicit `--host`/`--port` flags override them. Docker's internal API command and published ports still come from its deployment configuration. Change Compose port settings and recreate services when needed; a GUI review does not rewrite container mappings. The example systemd API command also has explicit bind arguments, which must be edited separately when changing its listening address.

Restored public assistants start disabled. Review the approved public documents, deployment domain and embedding paths before republishing.

## Docker migration

Download an administrator backup. Restore to a new named volume, retaining the old one for rollback:

~~~bash
docker compose down
docker volume create nelsonict_restored
~~~

Place the archive at backups/nelsonict-ai-backup.zip:

~~~bash
docker run --rm \
  -v nelsonict_restored:/app/data \
  -v "$PWD/backups:/backups:ro" \
  nelsonict-ai:local \
  python -m app.cli restore /backups/nelsonict-ai-backup.zip --destination /app/data
~~~

New named volumes inherit the image directory's ownership. Bind mounts need permissions for container UID 10001.

Change the final volume declaration in compose.yaml:

~~~yaml
volumes:
  nelson_data:
    external: true
    name: nelsonict_restored
~~~

Copy models/embeddings, review .env, and run:

~~~bash
docker compose up -d
~~~

Sign in and load a model through the GUI. Keep the old volume until recovery is verified.

## Updates

Back up, stop services, pull the new source, review schema notes, rebuild dependencies/images, restart, and verify sign-in, retrieval, and inference.

Schema version 3 is current. Versions 1 and 2 migrate automatically and transactionally, retaining existing records. Back up before upgrade and stop both services first. Versions newer than 3 are rejected. Keep the pre-migration backup for rollback; old code cannot open the new database.

## Troubleshooting

| Symptom | Action |
|---|---|
| Missing setup token | Run python -m app.cli setup-token using the API's data directory. |
| Empty model list | Copy GGUF into the configured models folder and refresh. |
| Load error | Check model architecture support, file integrity, RAM, and inference build. |
| No llama_cpp module | Install requirements-inference.txt or rebuild Docker. |
| GPU setting has no effect | Install an accelerated inference build; default Docker is CPU-only. |
| Worker offline | Start app.worker or inspect Docker worker logs. |
| Scanned PDF failed | Install OCR packages, Tesseract, and language data. |
| Embedding mismatch | Restart with the correct directory and reindex all affected documents. |
| Invalid host | Add the actual hostname/IP to NELSON_ALLOWED_HOSTS and restart. |
| No session over HTTP | Use HTTPS; disable secure cookies only for local development. |
| Duplicate process / locked database | Stop duplicate services and use local storage. |
| Queue full/paused or model busy | Inspect Operations → Request queue. Wait or cancel, and pause admission before changing a busy model. |
| Historical source download fails | Original PDF was deleted; the chat excerpt remains. |

## Boundaries

One host and a bounded user group. No billing, SSO, email password recovery, horizontal scaling, or automatic model downloads. Original-document quotas do not limit total chat/embedding/backup/model storage; monitor disk use separately. Backups include every account's sensitive data.
