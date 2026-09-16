# Nelsonict AI 1.1

**A private, deployable chatbot for Nelsonict Services Limited.** Run a compatible GGUF language model on your own computer or server, upload document knowledge, and keep accounts, conversations, original documents, extracted passages, and embeddings in SQLite.

[![Application checks](https://github.com/edunelsonit/nelsonict-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/edunelsonit/nelsonict-ai/actions/workflows/ci.yml)

## Contents

- [Features](#included)
- [Requirements](#requirements)
- [Docker quick start](#quick-start--docker-cpu)
- [Ubuntu / Debian installation](#native-installation--ubuntu--debian)
- [Windows and macOS](#windows-and-macos)
- [First-run setup and daily use](#first-run-setup-and-daily-use)
- [Configuration reference](#configuration-reference)
- [Upgrading from 1.0](#upgrading-from-10)
- [GGUF models and hardware](#gguf-models-and-hardware)
- [Document knowledge and sharing](#document-knowledge)
- [Optional semantic search](#optional-semantic-search)
- [Answer quality](#answer-quality)
- [Backup and migration](#backup-and-migration)
- [Deployment](#deployment)
- [Security and data storage](#security-and-data-storage)
- [API reference](#api-reference)
- [Troubleshooting](#troubleshooting)
- [Source structure](#source-structure)
- [Development and verification](#development-and-verification)
- [Contributing](#contributing)
- [Licence](#licence)

## Included

- Responsive browser interface with light/dark themes; no frontend build or CDN dependency.
- Administrator and member accounts, Argon2 passwords, HTTP-only sessions, CSRF checks, login throttling.
- Setup wizard with RAM/CPU/GPU/dependency checks and a local model test.
- Private knowledge bases with explicit reader/editor sharing and personal assistants.
- GGUF browser import with SHA-256 verification and saved model profiles.
- Local GGUF loading/unloading, CPU/GPU/context controls through llama-cpp-python.
- Streaming responses, stop generation, persistent history, rename, delete, and JSON export.
- Follow-up questions, full-document summaries, comparisons, and clickable source previews.
- PDF, DOCX, TXT, Markdown, CSV and XLSX ingestion, plus optional PDF OCR and a durable processing queue.
- SQLite FTS5 keyword retrieval; optional local semantic embeddings and hybrid search.
- Downloadable consistent backups and offline restore into a new data directory.
- Native installation, Docker Compose, Caddy/systemd examples, and automated tests.

**PDF “training” means retrieval-augmented generation (RAG).** Uploading PDFs does not change GGUF model weights. Relevant passages are supplied to the model at question time. Fine-tuning, LoRA training, and model conversion are not included.

### New in 1.1

| Update | What you can do |
|---|---|
| 1. Guided setup | Check hardware and dependencies, apply suggested CPU settings, and test the loaded model. |
| 2. Document analysis | Ask follow-up questions, summarise complete selected documents, compare documents, and preview citations. |
| 3. More document formats | Add DOCX, TXT, Markdown, CSV, and XLSX alongside PDF and optional scanned-PDF OCR. |
| 4. Model management | Import GGUF files in the browser, check SHA-256 values, inspect metadata, and save configuration profiles. |
| 5. Shared knowledge | Give existing users reader or editor access to selected knowledge bases. |

## Requirements

| Component | Requirement |
|---|---|
| Server | A computer or VPS that can run long-lived Python processes or Docker containers. |
| Native runtime | Python 3.11 or 3.12, a working C/C++ build toolchain if inference wheels are unavailable, and SQLite with FTS5. |
| Docker runtime | Docker Engine/Desktop with the Compose plugin. |
| Language model | A compatible local `.gguf` file supplied by the operator. No model weights are bundled. |
| Memory | Enough for the model weights, context cache, operating system, document processing, and optional embeddings. The setup wizard reports available memory; fitting a model is not guaranteed. |
| Storage | Persistent local disk for SQLite, GGUF files, optional embedding models, import staging, and backups. |
| Browser | A modern browser with JavaScript, streaming fetch, and cookies enabled. |
| Optional OCR | Tesseract with the required language packs and `requirements-ocr.txt`. English OCR is included in Docker. |

Internet access is needed to obtain dependencies and models. Normal chat and document processing can operate offline after installation. There is no required external AI API key. GPU acceleration is optional and depends on your installed inference build.

## Quick start — Docker CPU

Install Docker Engine/Desktop with Compose, then:

~~~bash
git clone https://github.com/edunelsonit/nelsonict-ai.git
cd nelsonict-ai
cp .env.example .env
mkdir -p models embeddings
docker compose build
docker compose up -d
docker compose exec app python -m app.cli setup-token
~~~

The build compiles the native inference dependency and can take several minutes. Docker includes English OCR. Default search uses keywords, so no embedding download is necessary.

1. Open **http://localhost:8000**.
2. Paste the setup token printed by the final command.
3. Create an administrator username and password of at least 12 characters.
4. Use **Setup wizard** to check dependencies, then **Models → Import a GGUF file** (or copy one to the host models folder).
5. Open **Models → Refresh files**, select it, and click **Load model**.
6. Start with **4096 context**, **4 CPU threads**, **0 GPU layers**, and **512 response tokens**. Lower settings if memory is limited.
7. Run the wizard’s local model test, then open **Knowledge**, create a collection, and upload a supported document.
8. Wait for **Ready**, then choose **Document answers** and that knowledge base in Chat.

For questions without documents, choose **General chat**.

~~~bash
docker compose logs -f app worker
docker compose down
~~~

Stopping Compose preserves the named volume. **Do not use the -v option with down unless you intend to delete stored data.**

## Native installation — Ubuntu / Debian

Use Python 3.11 or 3.12; automated Linux checks use 3.12.

~~~bash
sudo apt update
sudo apt install -y python3 python3-venv python3-dev build-essential cmake libgomp1 tesseract-ocr tesseract-ocr-eng
git clone https://github.com/edunelsonit/nelsonict-ai.git
cd nelsonict-ai
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-inference.txt -r requirements-ocr.txt
cp .env.example .env
mkdir -p models embeddings
python -m app.cli setup-token
python -m app.cli run
~~~

The run command starts the web application and document worker. Keep the terminal open; Ctrl+C stops them.

Alternatively, run these in separate terminals in the same project directory/environment:

~~~bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
python -m app.worker
~~~

Use **one API process and one worker** per data directory. File locks reject duplicate instances. Do not use multiple Uvicorn workers or development reload with model loading.

## Windows and macOS

Docker Desktop provides the most consistent CPU installation. For Windows native installation:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-ocr.txt
pip install -r requirements-inference.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
Copy-Item .env.example .env
python -m app.cli setup-token
python -m app.cli run
~~~

If a matching inference wheel is unavailable, installation needs a supported C/C++ toolchain. Install Tesseract separately and add its executable to PATH for scanned PDFs.

On macOS, install Python, CMake, and Tesseract, then follow the native Python commands. Use ARM64 Python on Apple Silicon. GPU support requires a matching build.

Upstream installation: [llama-cpp-python](https://llama-cpp-python.readthedocs.io/en/latest/).

## First-run setup and daily use

### Create the administrator

Open the application and enter the locally generated setup token. Usernames must contain 3–64 letters, digits, underscores, dots, `@`, or hyphens. Passwords must contain 12–128 characters. The first account becomes an administrator; public self-registration closes afterward.

The token is kept in `data/setup-token.txt` for a native installation until setup completes. `python -m app.cli setup-token` prints it only before the first account exists. For Docker, run the command inside the app container as shown above.

### Complete the setup wizard

1. Review CPU, available RAM, free disk, dependency status, and worker heartbeat.
2. Choose **Use suggested CPU settings**, or adjust settings to match your hardware.
3. Open the model manager, import or select a GGUF file, and load it.
4. Return to the wizard and run **Run local model test**.
5. Open the document library if you want to add knowledge, then choose **Finish setup**.

Completion requires a loaded model and a successful test. The test checks basic generation, not answer accuracy. Changing or unloading the model clears the previous test result. GPU detection alone does not establish that your inference package supports GPU offloading.

### Chat with your documents

1. In **Knowledge**, create a collection with a descriptive name.
2. Upload supported files and wait for each document to show **Ready**.
3. In **Chat**, start a conversation and select **Document answers** and the collection.
4. Choose **Ask / follow up**, **Full summary**, or **Compare documents**.
5. Select documents when narrowing a question, summarising, or comparing. Summary requires at least one selected document; comparison requires at least two.
6. Ask a specific question, inspect the response, and open its cited sources.

For example: “What services are described in this document?”, “Summarise all sections and list unresolved questions”, or “Compare the requirements and deadlines in these two documents.” Answers depend on what your documents actually contain.

Choose **General chat** to converse without document retrieval. **Stop** ends generation cooperatively and retains the partial reply. You can rename conversations, delete them, and export their messages as JSON.

### Personal assistants and accounts

Create a personal assistant with a name, instructions, and an optional accessible knowledge base. Select the assistant when creating a conversation. Sharing its knowledge base does not share the assistant or conversation.

Administrators add accounts and enable or disable users under **Settings & backup → User accounts**. Knowledge-base owners manage collection sharing separately. To recover a password from the server, use the administration command in [Backup and migration](#backup-and-migration).

## Configuration reference

Copy `.env.example` to `.env` in the project directory. Restart both the app and worker after changing runtime configuration. These are the supplied `.env` defaults; blank embedding configuration means keyword-only retrieval.

| Variable | Default | Purpose |
|---|---|---|
| `NELSON_DATA_DIR` | `data` | Directory containing `nelsonict.sqlite3` and runtime files. |
| `NELSON_MODELS_DIR` | `models` | Directory containing local GGUF files. |
| `NELSON_EMBEDDING_MODEL` | blank | Local Sentence Transformers model directory; never a runtime download URL. |
| `NELSON_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated permitted request hostnames/IP addresses, without schemes or ports. |
| `NELSON_COOKIE_SECURE` | `false` | Set `true` when clients access the application through HTTPS. |
| `NELSON_SESSION_HOURS` | `24` | Session lifetime in hours. |
| `NELSON_MAX_UPLOAD_MB` | `25` | Maximum original document size. |
| `NELSON_USER_STORAGE_MB` | `250` | Original-document quota per collection owner, including uploads from editors. |
| `NELSON_MAX_PAGES` | `300` | Maximum pages per PDF. |
| `NELSON_MAX_CHUNKS` | `10000` | Maximum indexed passages per knowledge base. |
| `NELSON_INDEX_TIMEOUT` | `600` | Document-indexing subprocess timeout in seconds. |
| `NELSON_OCR_LANGUAGE` | `eng` | Installed Tesseract language code(s). |
| `NELSON_MAX_MODEL_MB` | `20480` | Maximum GGUF browser import size. |
| `NELSON_MAX_SUMMARY_CHUNKS` | `256` | Maximum passages for a complete summary or comparison. |
| `NELSON_BIND_ADDRESS` | `127.0.0.1` | Compose host-side listening address; not a native CLI bind setting. |
| `NELSON_PORT` | `8000` | Compose published host port; not a native CLI port setting. |
| `WITH_SEMANTIC` | `false` | Optional Compose build argument; add to `.env` to include semantic dependencies. |

Size settings labelled MB are implemented using 1,024 × 1,024 bytes. Original-file quotas do not cap the complete database size: extracted text, vectors, conversations, and SQLite overhead consume additional storage.

Compose explicitly sets the container data and model directories to `/app/data` and `/app/models`. The database uses the `nelson_data` named volume, models use `./models`, and embeddings use the read-only `./embeddings` mount. Setting a different host `NELSON_DATA_DIR` does not relocate that named volume; change the Compose volume configuration when relocating Docker data.

For native installation, choose the listening address with `python -m app.cli run --host 127.0.0.1 --port 8000`. Relative paths are resolved from the working directory, so start commands from the project root.

### Model settings

| Setting | Default | Accepted range / meaning |
|---|---|---|
| Context | `4096` | 1,024–32,768 tokens; the selected model may have a lower supported limit. |
| CPU threads | `4` | 1–128; select a sensible count for available CPU capacity. |
| GPU layers | `0` | −1–200; `0` uses CPU, `-1` requests all layers when the native build supports it. |
| Response tokens | `512` | 64–2,048 tokens, within the available context budget. |
| Temperature | `0.3` | 0–1.5. |
| Chat format | blank | Use GGUF metadata unless a compatible explicit override is needed. |

## Upgrading from 1.0

Back up and stop the old API/worker, pull this release, install the updated requirements (or rebuild Docker), then restart. Schema v1 migrates transactionally to v2; existing PDF files, accounts, chats and embeddings are retained. Do not run old code against a migrated database. Retain your pre-upgrade backup for rollback. The restore command accepts both schema versions.

See [the 1.1 upgrade guide](docs/UPGRADE-1.1.md) for new controls and migration details.

## GGUF models and hardware

The operator supplies model files. Choose a model supported by the installed inference version and check its own licence and chat-template requirements.

- Only local GGUF files inside NELSON_MODELS_DIR appear in the picker.
- Administrators can stream-import GGUF files up to NELSON_MAX_MODEL_MB (20,480 MB default). Files are staged, metadata checked, and atomically installed without overwriting an existing filename.
- Paste a publisher SHA-256 to verify the upload, or calculate a checksum through Inspect file. A checksum does not establish model trustworthiness.
- Saved profiles retain model filename, context, threads, GPU layers, response tokens, temperature and chat format. Apply a profile to the form, then click Load model.
- Docker's models mount is now writable for imports. The host directory must permit container UID 10001 to write; copying models manually remains available.
- Users cannot provide arbitrary model paths or download URLs.
- Leave chat format blank to use GGUF metadata; override only when the model requires it.
- Saved configuration reloads on startup. Load errors appear in Models.
- Loading a replacement may unload the old model first to free memory.
- The default Docker image is CPU-only. GPU layer settings do not add GPU support.
- Native NVIDIA/Metal/Vulkan acceleration requires the corresponding inference build.
- Account for weights, context cache, OCR, and optional embedding-model memory.
- One response runs at a time. Additional requests get HTTP 409 with a busy message; chat queuing is not included.
- Stop requests are checked between model steps. Long prompt evaluation/native calls may delay cancellation.
- Generation has a five-minute cooperative timeout. Partial output is saved after cancellation/errors.
- Context budgeting reserves room for the answer and template overhead; long prompts produce a clear error.

Inference runs on the **host computer/server**, not the visitor's browser.

## Document knowledge

Conversations and assistants remain personal. Collections are private by default. Their owner can grant access to existing accounts through **Knowledge → Share this knowledge base**:

| Role | Ask/search/download/preview | Upload/reindex | Delete documents/collection | Manage sharing |
|---|---|---|---|---|
| Reader | Yes | No | No | No |
| Editor | Yes | Yes | No | No |
| Owner | Yes | Yes | Yes | Yes |

Editor uploads count against the collection owner's storage quota. Revoking access blocks new retrieval and source downloads and cancels that user's active generation. Historical chat excerpts already received remain in that user's chat history. Administrators manage accounts and server settings; full backups contain all users' data.

Processing:
1. Validate/limit document bytes and save the original and checksum in SQLite.
2. Claim the durable queue entry and start a time-limited document subprocess.
3. Extract format-specific text; for PDF, attempt OCR on pages containing very little text.
4. Divide text into bounded overlapping passages and generate optional embeddings.
5. Publish all passages in one transaction after indexing succeeds.

Defaults: **25 MB/document, 250 MB original documents/collection owner, 300 pages/PDF, 10,000 passages/knowledge base, 600 seconds/indexing job**. Text, embeddings, and chats consume additional disk space beyond the original-file quota.

Document states are queued, processing, ready, and failed. Interrupted jobs are requeued when the worker restarts. Reindexing hides old passages until ready. Deleting a document removes its original file and searchable passages; historical conversation excerpts remain.

OCR requires requirements-ocr.txt, Tesseract, and the selected language pack. Docker includes English. Set NELSON_OCR_LANGUAGE after installing another language pack. Blank/mixed-layout PDFs may need manual preparation. Unlock password-protected PDFs before uploading.

### Format details

| Format | Extracted information | Source location |
|---|---|---|
| PDF | Text and optional OCR | Physical page |
| DOCX | Main-body paragraphs and top-level tables | Paragraph/table block |
| TXT / MD | UTF-8 text | Line range |
| CSV | UTF-8 rows with header labels | CSV row |
| XLSX | Stored/cached cell values, sheet labels | Sheet and row |

Legacy DOC/XLS must be converted first. XLSX formulas are not calculated; save a recalculated workbook or export CSV. Images, Word tracked changes, nested tables, headers/footers and arbitrary embedded objects are not comprehensively extracted. Office archives are limited to 100 MB unpacked; tabular extraction is bounded to 50,000 rows and 200 columns. No macros or formula code is executed.

## Optional semantic search

Keyword retrieval works offline immediately. For semantic matching, supply a **local Sentence Transformers model directory**.

~~~bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-semantic.txt
python scripts/download_embedding.py sentence-transformers/all-MiniLM-L6-v2 embeddings/all-MiniLM-L6-v2
~~~

The helper explicitly downloads while online; alternatively copy a complete model directory from another machine. Then set native configuration:

~~~dotenv
NELSON_EMBEDDING_MODEL=embeddings/all-MiniLM-L6-v2
~~~

For Docker set:

~~~dotenv
WITH_SEMANTIC=true
NELSON_EMBEDDING_MODEL=/app/embeddings/all-MiniLM-L6-v2
~~~

Rebuild and restart:

~~~bash
docker compose build
docker compose up -d --force-recreate
~~~

**Reindex every document in affected knowledge bases** when enabling or changing the embedding model. Fingerprint checking prevents incompatible vectors from silently mixing. Keep the embedding directory immutable while running; restart both services after replacing it.

Float32 vectors stay in SQLite. Retrieval selects only the user's chosen ready knowledge base, combines cosine similarity and FTS5 ranking, and supplies up to five passages within the context budget. Intended for bounded local collections, not millions of vectors.

[Sentence Transformers documentation](https://www.sbert.net/examples/sentence_transformer/applications/semantic-search/README.html).

## Answer quality

**Ask / follow up** includes the last two user questions from the same collection as context and retrieves evidence again. Old model answers and old source identifiers are not reused as evidence. If a pronoun is ambiguous, restate its subject.

**Full summary** processes every indexed passage in the selected documents through map/reduce, then writes a final answer. **Compare documents** requires at least two ready documents and covers both before comparing. Select files using the multiple-selection control (Ctrl/⌘ on desktop). Progress appears above the chat box. The default full-analysis limit is 256 passages across at most 8 documents and 15 minutes of cooperative analysis time. Oversized requests fail explicitly; sources are not silently sampled. Very small model contexts may be unable to combine intermediate notes.

Click a citation or **Preview source** to open a PDF page image or extracted non-PDF source unit. PDF rendering requires pypdfium2, included in the Docker image and OCR requirements. Previews and downloads recheck collection access.

In document-question mode, if no supporting passages are found, the app returns an insufficient-evidence message without generating a model answer. With passages, instructions require evidence-based answers, acknowledged gaps, and source identifiers. Unknown labels are flagged, never linked. Source panels use retrieved metadata rather than model-generated URLs.

**Citations do not guarantee correctness.** Relevance thresholds and instructions cannot guarantee grounded answers. PDF text is untrusted context, but prompting alone cannot fully prevent prompt injection. The model has no shell, browsing, or file-writing tools.

## Backup and migration

Use **Settings & backup → Download backup** as administrator. The archive contains a consistent SQLite snapshot, original documents, embeddings, account hashes, conversations, and a checksum manifest. GGUF weights, embedding model directories, and the host `.env` file are excluded. Sharing memberships and saved model profiles are included.

Backups are **not encrypted**. Store them securely. Checksums detect corruption, not malicious replacement. Restore only archives from trusted installations.

~~~bash
mkdir -p backups
python -m app.cli backup backups/nelsonict-backup.zip
python -m app.cli restore backups/nelsonict-backup.zip --destination data-restored
~~~

Stop services before restoring. Restore checks archive entries, checksum, database integrity, foreign keys, and schema. It requires a new/empty destination and never overwrites an existing installation. The current limit is **2 GiB uncompressed database data**.

After restore:
1. Set NELSON_DATA_DIR=data-restored in .env.
2. Copy GGUF and embedding folders.
3. Review model paths, allowed hosts, and HTTPS settings.
4. Start services and sign in again; saved sessions were revoked.
5. Use Models to review CPU/GPU/context settings; automatic loading was cleared.
6. Reindex documents if the embedding model changed.

Restore also clears the model auto-load configuration and setup-test state, requeues interrupted indexing, and marks interrupted replies accordingly. Saved profiles remain available; review them for the new machine before loading a model. Restore is a CLI operation; the browser provides backup download, not a restore wizard.

For Docker migration see [DEPLOYMENT.md](docs/DEPLOYMENT.md).

Forgotten-password recovery from the server:

~~~bash
python -m app.cli reset-password owner
~~~

The new password is prompted privately instead of appearing in shell history.

## Deployment

After dependencies/models are installed, local and LAN operation needs no Internet. Browser assets use no external scripts, fonts, analytics, or AI APIs.

- Bind to localhost for personal use.
- Add the server IP/name to NELSON_ALLOWED_HOSTS for LAN access.
- For public use, configure HTTPS and NELSON_COOKIE_SECURE=true.
- Keep SQLite on persistent local storage, not an NFS/SMB share.
- Use one API and one worker. Measure latency before increasing user counts.
- Apply worker memory limits: subprocess timeouts alone do not bound RAM.
- GPU Docker deployment and capacity benchmarking are operator-specific.
- Shared cPanel hosting is generally unsuitable for a resident native model; use a server where you control long-running processes and memory.

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for LAN, HTTPS, migration, and systemd.

### LAN deployment

For a native server at an example address of `192.168.1.50`, add that address to `.env`:

~~~dotenv
NELSON_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.50
~~~

Then start:

~~~bash
python -m app.cli run --host 0.0.0.0 --port 8000
~~~

For Docker, also set `NELSON_BIND_ADDRESS=0.0.0.0`, then recreate the services. Browse to `http://192.168.1.50:8000` from an authorised device; replace the example IP with your server's address and configure its firewall accordingly. Plain HTTP does not encrypt credentials or document traffic; use HTTPS for networks where that is required.

### HTTPS and service management

The repository includes [a Caddy example](deploy/Caddyfile) and [API](deploy/nelsonict-ai.service) / [worker](deploy/nelsonict-worker.service) systemd units. Replace the sample domain and paths, create the service account, and grant it access to the data/model directories before installing the units.

For a public domain, configure DNS, allow the domain in `NELSON_ALLOWED_HOSTS`, set `NELSON_COOKIE_SECURE=true`, and proxy to the loopback-bound application. The Caddy example allows a larger body specifically for model import; align proxy and application limits with your intended upload sizes. Keep response streaming enabled. See [deployment instructions](docs/DEPLOYMENT.md) for the complete procedure.

GitHub hosts this source repository; GitHub Pages cannot run its Python API, SQLite database, or GGUF inference. Deploy the runtime on a suitable computer or server.

## Security and data storage

- Passwords are hashed with Argon2; session cookies are HTTP-only and SameSite Strict. HTTPS deployments must also enable secure cookies.
- Authenticated mutations require the session's CSRF token. Login and initial setup require the application client header, and cross-site requests are checked.
- Account and collection permissions are checked on retrieval, original downloads, and source previews. An application administrator does not automatically receive collection access through ordinary collection APIs.
- Administrators can download a complete backup, and server operators can access stored data. This is not end-to-end encryption or protection from the machine's administrator.
- SQLite contains account password hashes, sessions, knowledge membership, original documents, extracted passages, optional embedding vectors, assistants, conversations, and model settings/profiles. It is not encrypted by the application.
- The database uses WAL, foreign keys, FTS5 indexes, and transactions. Keep it on persistent local storage. Use the snapshot backup command instead of copying only the live `.sqlite3` file while writes are occurring.
- Uploads are bounded and filenames are constrained. Office archive limits and subprocess timeouts reduce resource exposure but do not replace operating-system memory limits.
- GGUF inspection checks metadata and structure headers; it does not fully validate tensor payloads or guarantee that a model can load. A matching publisher SHA-256 verifies matching bytes, not the publisher's safety claims.
- Removing a document or revoking access cannot retract excerpts already saved in another user's conversation or exported files.

Do not commit `.env`, databases, backups, private documents, or model files. Use filesystem permissions and host/disk encryption appropriate to your deployment.

## API reference

Open `/docs` on your running instance for the local API reference and `/openapi.json` for the machine-readable schema. Documentation assets are served locally.

| Area | Selected endpoints |
|---|---|
| Health and setup | `GET /api/health`, `GET /api/setup`, `POST /api/setup` |
| Session | `POST /api/login`, `GET /api/me`, `POST /api/logout` |
| Accounts (admin) | `GET/POST /api/users`, `POST /api/users/{id}/disable`, `POST /api/users/{id}/enable` |
| Wizard (admin) | `GET /api/system/check`, `POST /api/system/model-test`, `POST /api/system/complete` |
| Knowledge | `GET/POST /api/knowledge`, `DELETE /api/knowledge/{id}` |
| Documents | `GET/POST /api/knowledge/{id}/documents`, `GET /api/documents/{id}/download`, `GET /api/documents/{id}/preview`, `POST /api/documents/{id}/reindex`, `DELETE /api/documents/{id}` |
| Sharing (owner) | `GET/POST /api/knowledge/{id}/members`, `DELETE /api/knowledge/{id}/members/{member_id}` |
| Assistants | `GET/POST /api/assistants`, `PUT/DELETE /api/assistants/{id}` |
| Conversations | `GET/POST /api/conversations`, `PUT/DELETE /api/conversations/{id}`, `GET /api/conversations/{id}/messages`, `GET /api/conversations/{id}/export` |
| Streaming chat | `POST /api/conversations/{id}/chat`, `POST /api/conversations/{id}/stop` |
| Model management (admin) | `GET /api/models`, `POST /api/models/load`, `POST /api/models/unload`, `POST /api/models/import`, `GET /api/models/inspect` |
| Profiles (admin) | `GET/POST /api/model-profiles`, `DELETE /api/model-profiles/{id}` |
| Status and backup | `GET /api/status`, `GET /api/backup` (backup is admin-only) |

### Request conventions

1. Log in with a JSON username/password body and `X-Nelson-Client: web`; retain the returned `nelson_session` cookie and `csrf` value.
2. Send the cookie on authenticated requests. For authenticated mutations, also send `X-Nelson-Client: web` and `X-CSRF-Token: <csrf value>`.
3. For document upload, send raw file bytes, not multipart form data, and a URL-encoded `X-Filename` header.
4. Model import uses raw bytes and `X-Filename`, with an optional expected hexadecimal `X-SHA256` value.
5. Chat uses a streaming POST response, so clients should use streaming fetch or an equivalent HTTP client rather than native browser `EventSource`, which issues GET requests.

Example chat JSON for an existing conversation and accessible collection (replace IDs):

~~~json
{
  "content": "What are the main requirements in these documents?",
  "mode": "documents",
  "kb_id": 1,
  "task": "question",
  "document_ids": [1, 2]
}
~~~

Use `task: "summary"` or `task: "compare"` for complete analysis. For general chat use `mode: "general"`, `task: "question"`, and omit collection/document selections. Streaming messages contain JSON event objects such as `sources`, `token`, `error`, and `done`; full analysis also reports progress. Handle errors after streaming starts as well as HTTP errors before the stream opens.

## Troubleshooting

| Symptom | What to check |
|---|---|
| Model list is empty | Place a `.gguf` file in the configured models directory, or import it as administrator, then refresh. For Docker use the host `./models` bind mount. |
| GGUF import permission error | Check directory ownership and permissions for the running service. Docker uses UID `10001`; give it write access to the model directory, or copy models manually. |
| Import rejected / checksum mismatch | Confirm the upload limit, available staging space, expected publisher hash, valid GGUF metadata, and that the destination filename is not already present. Also check the reverse proxy body limit. |
| Model load fails | Read the load error, check inference installation and model compatibility, lower context/GPU settings, and verify available memory. Metadata inspection alone does not prove a file loads. |
| GPU detected but inference uses CPU | Install a native inference build for that accelerator. The default container is CPU-only; changing the layer count does not change its build. |
| HTTP 409 / model busy | Wait for the active response or stop it. Model operations and generation are serialised; there is no waiting chat queue. |
| Stop takes time | Cancellation waits for a native model step to return. Large prompt evaluation can delay it. |
| Documents stay queued | Check worker logs and heartbeat. Start the worker with the same `.env` and data directory as the API. |
| Document indexing fails | Inspect the document error; check format, encryption, OCR installation, page/row/size limits, memory, and indexing timeout. |
| Scanned PDF produces little text | Install OCR requirements, Tesseract, and the selected language pack. Confirm scan quality; complex layouts may need preparation. |
| DOCX/XLSX content appears missing | Only supported extracted text/cached cells are indexed. Recalculate and save spreadsheets externally; convert unsupported structures to a suitable PDF or text file. |
| Answers say no supporting evidence | Confirm document status is Ready, correct collection and filters are selected, and the wording matches indexed content. Consider optional semantic search. |
| Semantic fingerprint mismatch | Restart both services with the intended embedding model directory, then reindex affected documents. |
| Full summary is too large | Select fewer documents or adjust `NELSON_MAX_SUMMARY_CHUNKS` with sufficient resources. Increasing the limit does not remove model-context or analysis-time constraints. |
| PDF preview unavailable | Install `pypdfium2` through OCR requirements and check collection access. Non-PDF previews show extracted source text. |
| Invalid host / HTTP 400 | Add the actual server hostname/IP to `NELSON_ALLOWED_HOSTS` and restart. |
| Login succeeds but session is lost over HTTP | A secure cookie requires HTTPS. Use HTTPS or set `NELSON_COOKIE_SECURE=false` for a local HTTP installation. |
| CSRF / HTTP 403 | Sign in again and send the current CSRF/client headers for API mutations; use the correct same-origin app URL. |
| Sharing fails | Use an existing active account's exact username. Only the collection owner manages memberships. |
| Duplicate-process lock error | Stop the existing API/worker and run exactly one of each per data directory. Do not enable multiple Uvicorn workers. |
| Restore refuses destination | Select a new or empty directory. Restore deliberately does not overwrite an existing installation. |
| Replies arrive all at once behind a proxy | Review proxy buffering and timeout settings; use the supplied streaming Caddy example. |

Useful diagnostic commands:

~~~bash
# Docker services and recent logs
docker compose ps
docker compose logs --tail=100 app worker

# Basic HTTP health (not proof that a model is loaded or the worker is healthy)
curl --fail http://127.0.0.1:8000/api/health

# Native command help
python -m app.cli --help
~~~

## Source structure

| Path | Responsibility |
|---|---|
| app/main.py | Authentication, accounts, knowledge, chat, model controls |
| app/db.py | SQLite schema, transactions, FTS5 triggers |
| app/security.py | Sessions, ownership, passwords, throttling |
| app/inference.py | GGUF lifecycle, context budgeting, generation |
| app/retrieval.py | Chunking, embeddings, authorised hybrid search |
| app/index_document.py | PDF extraction, OCR, atomic indexing |
| app/features.py | Setup checks, model import/profiles, sharing, preview APIs |
| app/formats.py | Bounded Office/text/table extraction |
| app/document_chat.py | Complete selected-document map/reduce |
| app/machine.py | Hardware/dependency and GGUF metadata inspection |
| app/worker.py | Persistent queue and subprocess timeouts |
| app/maintenance.py | Snapshot and validated restore |
| app/cli.py | Start, setup, backup, restore, password recovery |
| app/static/ | HTML/CSS/JavaScript application |
| tests/ | API, isolation, retrieval, streaming, recovery tests |
| deploy/ | Proxy and service examples |

Implementation uses FastAPI, SQLite directly, and a self-contained JavaScript frontend. React, npm, Redis, a separate vector database, and cloud AI keys are not required.

## Development and verification

Version 1.1 local verification: **49 Python tests passed**, including the 24 original regression tests. DOM smoke checks passed for setup, navigation, profiles, sharing, document listing and summary selection. The browser preview could not connect to the local address, so visual rendering was not verified. Docker and real-GGUF/GPU testing remain unverified in this session; generation tests use a simulated model boundary.

See [API reference](#api-reference) for endpoint groups and authentication/upload conventions.

~~~bash
pip install -r requirements-dev.txt
python -m pytest -q
node --check app/static/app.js
node --check app/static/api-docs.js
~~~

Optional frontend DOM smoke checks on Linux/macOS with Node.js 22 and npm:

~~~bash
npm install --prefix /tmp/nelsonict-ui jsdom@30.0.1 --no-audit --no-fund
NODE_PATH=/tmp/nelsonict-ui/node_modules node tests/ui-smoke.cjs
~~~

Node/npm are development-only dependencies. The installed application serves static frontend files directly.

Tests use real generated PDFs and temporary databases. Generation is simulated to exercise streaming/failure paths without downloading a large model. The CI workflow is configured to build native inference/OCR dependencies and check imports and HTTP startup. At the last implementation verification, hosted Actions jobs failed before executing steps, so no successful hosted run or container verification is claimed; consult the workflow badge for current status. Resolved Python versions are recorded as an artifact. Bounded dependency ranges are not a complete transitive lockfile.

**Not established by these checks:** your GGUF's answer quality, GPU compatibility, real scanned-PDF OCR accuracy, full semantic-model integration, browser visual rendering, or sustained multi-user load. Complete the [target-machine acceptance checklist](docs/ACCEPTANCE.md).

## Contributing

Use a feature branch and describe the problem, change, and verification in your pull request. Run the Python tests for backend changes and the JavaScript checks for frontend changes. Add regression coverage for permission, retrieval, migration, or streaming behaviour when changing those areas.

Report reproducible problems through [GitHub Issues](https://github.com/edunelsonit/nelsonict-ai/issues). Include the operating system, Python/container version, installation method, relevant error, and steps to reproduce. Remove passwords, cookies, setup tokens, document contents, and other private data from reports. For inference failures, include model architecture/quantisation and hardware details without uploading the weights.

Further documentation:

- [Deployment, HTTPS, systemd, and Docker migration](docs/DEPLOYMENT.md)
- [Version 1.1 upgrade and feature guide](docs/UPGRADE-1.1.md)
- [Target-machine acceptance checklist](docs/ACCEPTANCE.md)

## Licence

The repository's existing **GNU GPL v3** licence is retained in [LICENSE](LICENSE). Models and third-party dependencies have their own licences.

Copyright © 2026 Nelsonict Services Limited.
