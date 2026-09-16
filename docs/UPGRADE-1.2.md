# Nelsonict AI 1.2 — options 6–10

This release adds guided migration, a bounded FIFO request queue, feedback and evaluation, desktop packaging, and an anonymous website assistant. Existing accounts, PDF/document knowledge, assistants, chats, memberships and model profiles remain intact. Schema versions 1 and 2 migrate to version 3 at startup.

## Upgrade an existing installation

1. Download a backup and copy your `.env`, GGUF files and optional embedding-model directory separately.
2. Stop the API and worker. Keep the pre-upgrade backup for rollback.
3. Pull the updated source and install requirements, or rebuild the Compose image.
4. Start one API and one worker. Startup performs the database migration.
5. Sign in, check the model and worker, and run your target-machine acceptance checks.

Do not run old code against the migrated database. To roll back, restore a pre-upgrade backup into a new directory and run the corresponding older source version against that directory.

## 6. Guided backup and migration

**Settings & backup → Download backup** produces a consistent SQLite snapshot. On the target computer, install Nelsonict AI, complete its initial administrator setup, and open **Guided restore & migration**.

1. Upload a trusted backup ZIP. Upload progress is displayed; validation then checks entries, checksum, SQLite integrity, foreign keys and supported schema.
2. Review account, collection, document and conversation counts. The restore goes into a new folder under the stable bootstrap data directory: `restores/<random-id>/data`.
3. Review that data path and enter existing absolute server paths for GGUF and optional embedding directories. A browser file path on your laptop is not a server path.
4. Review allowed hostnames/IPs, the listening address/port, HTTPS cookies, CPU threads, context and GPU layers.
5. Type `RESTORE` and prepare activation. This explicit action writes `runtime-settings.json` in the original bootstrap data directory. Existing running processes and their current data stay unchanged until restart.
6. Restart both API and worker. A launcher started with `python -m app.cli run`, or the desktop application, supports the **Restart managed application** button. For Compose, use `docker compose restart app worker`; for systemd, restart both units.
7. Reopen the reviewed address and sign in using an account from the backup. Old sessions are revoked. Load and test a compatible GGUF through the setup wizard. Reviewed hardware suggestions are available there; weights are never automatically loaded after restore.

Original files and old data remain in place. A staged restore can be discarded before activation. An active or pending restore cannot be removed through that control. Abandoned stages remain on disk until discarded; they contain private backup data.

### Network and deployment details

The GUI cannot change a container's published ports or your operating system's firewall. For Docker, update `NELSON_BIND_ADDRESS` / `NELSON_PORT` in Compose configuration and recreate services if the public binding must change. Internal Uvicorn still listens on the container's configured port. Systemd units with explicit `--host`/`--port` arguments also need corresponding edits. Configure HTTPS at your reverse proxy and add the external domain to allowed hosts.

Keep the original bootstrap directory and its runtime overlay available: both processes read that same overlay at startup. Changing `NELSON_DATA_DIR` externally to a different bootstrap root bypasses that overlay. Models and embedding directories must remain accessible inside your container if applicable.

For manual rollback of an activation, stop both processes and copy `previous-runtime-settings.json` over `runtime-settings.json` in the bootstrap directory, then restart. This returns to the prior data path; it does not undo subsequent writes in either database. Back up each database you need to keep.

Backup archives remain unencrypted. The upload defaults to 2,048 MiB; the restored SQLite database is limited to 2 GiB uncompressed. The supplied Caddy example includes a separate backup-upload limit. Restored public assistants are disabled and must be reviewed and explicitly enabled again. Running evaluations become interrupted.

## 7. Multiple-user request queue

Private chats, evaluation runs, and public website requests share one model and a FIFO queue. Waiting chat streams display their position. Position zero in the administration view means running; positive positions include requests ahead of the waiter, including the active request.

- **Stop** cancels your active or waiting chat. Queue cancellation removes a waiting ticket immediately; active native generation stops cooperatively.
- Administrators use **Operations & website → Request queue** to inspect, cancel or pause requests.
- **Pause** blocks new admission and holds waiting requests. It does not stop the active response. Pause, cancel the active response, wait for it to release the model, then change the model and resume.
- A user can inspect and cancel their own tickets through `/api/queue`; administrators can manage all tickets.
- Administrators' account, queue and document controls do not wait for inference to finish. Loading/unloading still requires an idle model.
- Access is checked again when a queued document request starts. Revoking membership or disabling a user cancels their private queued requests.

Defaults: 32 total admitted requests, 2 per user, and 600 seconds of waiting time. Anonymous public requests share user slot `0`, so the default permits at most two public requests across all sites together. There is also a per-site/IP rate limit of ten requests per five minutes. Forwarded client-IP handling depends on a correctly configured trusted reverse proxy.

The queue is in memory. Restarting cancels waiting/running requests; incomplete private messages and evaluations are marked interrupted on startup. Re-submit a request after a restart. Long native prompt evaluation may delay cancellation. Evaluation runs process up to 20 questions in one queue slot; use small sets on shared installations.

## 8. Answer feedback and evaluation

Each saved assistant response offers **Helpful**, **Flag incorrect**, and **Remove feedback**. Submitting feedback asks whether to share the answer, its cited excerpts, and your note with administrators. This is an explicit exception to ordinary conversation privacy. Only the owner of an answer can submit its feedback. Administrators review the latest 200 submitted reports in **Quality & evaluation**.

Build a personal question set under **Quality & evaluation**:

1. Select a knowledge base, write a question, and record the expected answer or key facts.
2. Save, edit or delete questions. Each user may maintain up to 200 questions.
3. Select 1–20 questions and run an evaluation using the loaded local model.
4. Open the run to inspect its status, configuration, model SHA-256 when available, answers and sources. Runs use the same bounded queue; waiting/running runs can be cancelled.
5. Compare answers with expected facts and sources, then mark individual results **pass** or **fail** with a review note.
6. Export run JSON to compare before/after versions or keep an external record.

The displayed **expected-term coverage** measures overlap between unique words in the expected answer and generated answer. It is not factual accuracy, semantic similarity, a confidence score or an LLM judge. Human review is required. A run snapshots its questions, references, answers and model configuration, so later question edits do not rewrite previous results. Source excerpts are retained like chat history; revocation cannot retract previously received evidence.

## 9. Desktop installation packages

See [DESKTOP.md](DESKTOP.md) for Windows installer and Ubuntu `.deb` build/install procedures, shortcuts, per-user startup, update controls, and validation limits. The launcher manages the API and document worker; model files are still supplied separately.

## 10. Website integration

See [WEBSITE.md](WEBSITE.md) for the approved-public-information workflow and iframe integration for `nelsonict.com.ng`. The feature is disabled until an administrator creates a separate public collection and explicitly publishes selected ready documents. Adding this feature to the repository does not edit your website automatically.

## Additional environment variables

| Variable | Default | Purpose |
|---|---|---|
| `NELSON_QUEUE_LIMIT` | `32` | Total admitted model requests, including the active request. |
| `NELSON_QUEUE_PER_USER` | `2` | Requests per signed-in account; public requests share account slot 0. |
| `NELSON_QUEUE_TIMEOUT` | `600` | Maximum waiting time in seconds. |
| `NELSON_MAX_BACKUP_MB` | `2048` | Maximum GUI backup ZIP upload, in MiB. |
| `NELSON_BIND_HOST` | `127.0.0.1` | Default native managed-launch bind address; explicit CLI flags override it. |
| `NELSON_BIND_PORT` | `8000` | Default native managed-launch port; explicit CLI flags override it. |

Runtime migration overrides are saved separately from `.env`. Do not confuse native `NELSON_BIND_HOST`/`NELSON_BIND_PORT` with Compose's host-side `NELSON_BIND_ADDRESS`/`NELSON_PORT`.

## New API groups

All private mutation endpoints retain session, client-header and CSRF protections. See `/docs` and `/openapi.json` for complete schemas.

| Group | Routes |
|---|---|
| Migration | `GET /api/migration/settings`, `POST /api/migration/stage`, `POST /api/migration/{id}/activate`, `DELETE /api/migration/{id}`, `POST /api/migration/restart` |
| Queue | `GET /api/queue`, `POST /api/queue/pause`, `POST /api/queue/cancel` |
| Feedback | `POST/DELETE /api/messages/{id}/feedback`, `GET /api/feedback` |
| Question set | `GET/POST /api/evaluation/questions`, `PUT/DELETE /api/evaluation/questions/{id}` |
| Evaluations | `GET/POST /api/evaluation/runs`, `GET /api/evaluation/runs/{id}`, `POST /api/evaluation/runs/{id}/cancel`, `POST /api/evaluation/runs/{id}/review` |
| Public administration | `GET/POST /api/public-sites`, `PUT/DELETE /api/public-sites/{id}` |
| Anonymous widget | `GET /widget/{id}`, `POST /api/public/{id}/chat`, `POST /api/public/{id}/cancel/{token}` |
