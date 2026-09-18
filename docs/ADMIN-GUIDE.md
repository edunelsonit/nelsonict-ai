# Administrator guide

This guide covers routine operation of Nelsonict AI 1.2. Use the [project README](../README.md) for installation and the [deployment guide](DEPLOYMENT.md) for network/service configuration.

## First-run setup

Start one API process and one document worker against the same data directory. Obtain the setup token locally with `python -m app.cli setup-token`, from `data/setup-token.txt`, or through **Copy first-run setup token** in the desktop launcher. In Docker run the CLI command inside the app container.

Create the first administrator through the browser. Public registration closes after that first account. The setup wizard checks available hardware, dependencies, writable model storage and worker heartbeat. Import or copy a GGUF, load it, run the local model test and complete setup. A successful short response verifies basic inference, not answer quality.

## Manage accounts and access

Create member or administrator accounts in **Settings & backup → User accounts**. Use individual accounts rather than sharing an administrator login. Enable/disable accounts there as needed; you cannot disable your own account through that control. Disabling an account revokes its sessions and cancels its private queued/active requests.

For server-side password recovery:

```bash
python -m app.cli reset-password username
```

The CLI prompts for the new password and confirmation, revokes sessions and re-enables the account. Run it with the installation's configuration and data directory.

Collection owners manage reader/editor memberships. Administrator status does not automatically grant ordinary API access to all private collections or conversations. Administrators can download complete backups and see explicitly submitted answer reports; server operators can access the underlying files.

## Choose and manage models

Use **Models** to import a local GGUF, optionally match a publisher SHA-256, inspect metadata, load/unload, and save profiles. Import stages a file and installs it without overwriting an existing filename. The default upload limit is 20,480 MiB. Model imports need space for staging and a writable model directory.

Start with CPU settings appropriate to the available memory and cores. Model weights, context cache, document processing and optional embeddings all consume RAM. GGUF header/metadata inspection does not validate all tensor data or establish compatibility. GPU settings require a corresponding native inference build; the standard Docker image is CPU-only.

Applying a saved profile only fills the form; click **Load model** to activate it. Normal startup attempts to reload the last model configuration. Restoring a backup clears automatic loading and requires review on the target computer.

## Keep the queue manageable

Open **Operations & website → Request queue** to see request type, account, state and position. Private chat, evaluation and anonymous public requests share a single model.

To change models during a busy period:

1. Pause the queue to block new requests and hold waiters.
2. Cancel the active request and wait for native inference to release the model.
3. Change or unload the model.
4. Resume admission and waiting requests.

Pause alone does not stop the active request. Cancellation is cooperative during native generation. Defaults are 32 admitted requests, two per account, and 600 seconds waiting. Public requests share account slot 0 across sites. The queue is in memory; restart interrupts it rather than recovering waiting positions.

Use small evaluation batches when other people are waiting: a run holds its slot while processing up to 20 questions. Queue management, account and ordinary document controls do not wait for model inference, but changing the model itself requires its exclusive lock.

## Maintain document indexing

The worker processes durable SQLite queue entries in separate, time-limited subprocesses. Interrupted processing is requeued at worker startup. Reindexing hides the document's old searchable passages until processing succeeds.

Check worker heartbeat and errors before re-uploading files. Review OCR installation, page/format limits, memory and the indexing timeout for failures. Set worker memory limits at the OS/container level; a time limit alone does not bound RAM.

If you enable or change the embedding model, restart both processes and reindex affected documents. Keep the embedding directory unchanged while running. A mismatched model fingerprint prevents incompatible vectors from silently mixing.

## Back up and restore

Use **Download backup** or:

```bash
mkdir -p backups
python -m app.cli backup backups/nelsonict-backup.zip
```

Choose a new filename for each backup; the CLI refuses overwrite. The snapshot includes all accounts, documents, extracted passages, embeddings, conversations, memberships, feedback, evaluations and public publication settings. GGUF weights, embedding-model folders, host `.env` and the external migration runtime overlay are not included. Preserve those separately as needed.

Backups are unencrypted. Checksum verification detects corruption, not malicious replacement. Restore trusted archives only, and periodically prove recovery on a separate directory or machine.

The guided restore workflow validates a ZIP in an isolated directory, displays counts, and lets you review model paths, network and hardware settings. Preparing activation writes a runtime overlay in the stable bootstrap directory; switching happens after both processes restart. The existing data directory remains intact. See [the complete migration procedure](UPGRADE-1.2.md#6-guided-backup-and-migration) before activation or rollback.

For offline restore:

```bash
python -m app.cli restore backups/nelsonict-backup.zip --destination data-restored
```

Use a new/empty target, stop services before switching, and point both processes at the restored installation. Restored sessions are revoked; public assistants are disabled; model loading and wizard-test state are cleared. A 2 GiB uncompressed database is the current restore limit.

## Review quality and public information

Review opt-in answer reports in **Quality & evaluation**. Use a representative personal question set before changing models, prompts, extraction settings or embedding models. Inspect original evidence; expected-term coverage is only a lexical comparison.

Publish website information only through a separate public assistant collection and explicit ready-document approval. New uploads are not automatically published. Review service descriptions, contact details and other public facts before approval. The origin allowlist restricts browser embedding; it does not make a public endpoint private. See [website integration](WEBSITE.md).

## Routine operational checks

| Check | Why it matters |
|---|---|
| API health and document-worker heartbeat | HTTP health alone does not verify model readiness or worker operation. |
| Free disk and backup growth | Original-file quotas do not cap SQLite, logs, embeddings, weights or restore staging. |
| Model error and memory use | A successful previous load does not guarantee current hardware capacity. |
| Queue length and wait times | Sustained waits indicate load that the single model cannot serve promptly. |
| Recent failed documents | Repeated failures may require preparation or configuration changes. |
| Backup recovery | A downloadable archive is useful only if you can restore it. |
| Public document approval | Prevents accidental publication and stale website answers. |

Useful commands:

```bash
docker compose ps
docker compose logs --tail=100 app worker
curl --fail http://127.0.0.1:8000/api/health
```

For native managed launch use the GUI restart control or stop/start `python -m app.cli run`. For systemd or Docker restart both services with that manager. Avoid starting a desktop service, CLI supervisor and systemd API against the same data directory.

## Upgrade and recover

Back up, stop both services, update code/dependencies or rebuild containers, restart, then complete the [acceptance checklist](ACCEPTANCE.md). Schema 1/2 upgrades to schema 3; old code must not be run against the migrated database. Preserve the pre-upgrade backup and matching source version for rollback.

Desktop updates are operator-installed. **Check for updates** opens the official release page; the launcher does not silently download or execute installers. See [desktop packaging](DESKTOP.md) for platform requirements and validation limits.
