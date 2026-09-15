# Nelsonict AI 1.1 — options 1–5

## Upgrade safely

1. Download an administrator backup. Stop the API and worker.
2. Pull the updated repository.
3. Native: install requirements.txt, requirements-inference.txt and requirements-ocr.txt in your existing virtual environment. Docker: rebuild the image.
4. Review the new settings in .env.example and your model-folder permissions.
5. Start one API and one worker. Database schema 1 migrates to 2 automatically.
6. Open Setup wizard, refresh checks, select/load your existing model, and run the local model test.

Migration adds format/location metadata, collection membership, saved profiles and collection-scoped question history. Existing PDFs retain their original bytes, accounts, conversations, chunks and embeddings. There is no destructive table rebuild. Historical questions created by v1 have no collection scope and are not automatically used for follow-ups.

Backups from either schema can be restored into a new directory. A v1 restore migrates on startup. Restore revokes sessions and resets setup/model-test state. Saved model profiles remain, but their paths and hardware settings must be reviewed before loading on a different computer.

## Where to find each option

| Option | Screen | Workflow |
|---|---|---|
| 1 — Setup wizard | Setup wizard (administrator) | Check CPU/RAM/GPU/backend/dependencies, apply suggested CPU settings, load model, run test |
| 2 — Document conversations | Chat | Choose Ask/follow up, Full summary, or Compare documents; select ready files; click citations for previews |
| 3 — More formats | Knowledge | Upload PDF/DOCX/TXT/MD/CSV/XLSX; wait for Ready; inspect source locations |
| 4 — Model management | Models | Import local GGUF, optionally verify expected checksum, inspect metadata, save/apply profiles |
| 5 — Shared knowledge | Knowledge → select an owned collection | Grant reader/editor access by existing username; update or revoke membership |

No cloud model downloads or APIs are required. Model files, documents and embeddings remain on the host. GGUF metadata checks cannot guarantee that a model architecture is supported by the installed native runtime; loading and the wizard's test provide the next check.

## Operational limits

- Chat remains single-generation; full summaries/comparisons occupy that same model slot.
- Full analysis processes every indexed passage, up to 256 passages/8 documents by default. It can fail on small context windows instead of silently omitting sections.
- GPU detection does not enable acceleration automatically. Use a compatible native build.
- Shared editor uploads consume the collection owner's quota. Only owners delete documents or manage access.
- Revocation prevents future access but cannot retract excerpts already saved to another user's conversations.
- Native PDF previews require pypdfium2. The API serializes its rendering calls because PDFium is not thread-safe.
- The models directory must be writable for browser import. Docker now mounts it read/write; set host permissions for UID 10001 rather than granting universal write permissions.
- The default HTTPS proxy template now separates large authenticated model imports from smaller document uploads.

## Verification

49 Python tests passed locally, including original regressions, new extraction formats, sharing/revocation, PNG preview, checksums, profiles, wizard checks, follow-up scope, complete summaries/comparisons and database migration. JavaScript syntax/DOM-ID checks and DOM smoke tests passed. These use simulated language-model generation. Actual GGUF quality, GPU behavior, Docker build and browser visual appearance remain target-machine checks.
