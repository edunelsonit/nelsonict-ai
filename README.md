# Nelsonict AI 1.1

**A private, deployable chatbot for Nelsonict Services Limited.** Run a compatible GGUF language model on your own computer or server, upload document knowledge, and keep accounts, conversations, original documents, extracted passages, and embeddings in SQLite.

[![Application checks](https://github.com/edunelsonit/nelsonict-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/edunelsonit/nelsonict-ai/actions/workflows/ci.yml)

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

The run command starts the web application and PDF worker. Keep the terminal open; Ctrl+C stops them.

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
3. Extract text by page and attempt OCR on pages containing very little text.
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

Without passages, the app answers without calling the model. With passages, instructions require evidence-based answers, acknowledged gaps, and source identifiers. Unknown labels are flagged, never linked. Source panels use retrieved metadata rather than model-generated URLs.

**Citations do not guarantee correctness.** Relevance thresholds and instructions cannot guarantee grounded answers. PDF text is untrusted context, but prompting alone cannot fully prevent prompt injection. The model has no shell, browsing, or file-writing tools.

## Backup and migration

Use **Settings & backup → Download backup** as administrator. The archive contains a consistent SQLite snapshot, original documents, embeddings, account hashes, conversations, and a checksum manifest. Model weights are excluded.

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
6. Reindex PDFs if the embedding model changed.

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

API documentation is at /docs. Mutations require a session cookie, X-Nelson-Client: web, and the X-CSRF-Token returned at login. Document uploads use raw file bytes and a URL-encoded X-Filename header. Model imports use the same header plus optional X-SHA256.

~~~bash
pip install -r requirements-dev.txt
python -m pytest -q
node --check app/static/app.js
~~~

Tests use real generated PDFs and temporary databases. Generation is simulated to exercise streaming/failure paths without downloading a large model. Docker CI builds native inference/OCR dependencies and checks imports and HTTP startup. Resolved Python versions are recorded as an artifact. Bounded dependency ranges are not a complete transitive lockfile.

**Not established by these checks:** your GGUF's answer quality, GPU compatibility, real scanned-PDF OCR accuracy, full semantic-model integration, browser visual rendering, or sustained multi-user load. Complete the [target-machine acceptance checklist](docs/ACCEPTANCE.md).

## Licence

The repository's existing **GNU GPL v3** licence is retained in [LICENSE](LICENSE). Models and third-party dependencies have their own licences.

Copyright © 2026 Nelsonict Services Limited.
