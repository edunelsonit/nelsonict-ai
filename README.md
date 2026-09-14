# Nelsonict AI

**A private, deployable chatbot for Nelsonict Services Limited.** Run a compatible GGUF language model on your own computer or server, upload PDF knowledge, and keep accounts, conversations, original PDFs, extracted passages, and embeddings in SQLite.

[![Application checks](https://github.com/edunelsonit/nelsonict-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/edunelsonit/nelsonict-ai/actions/workflows/ci.yml)

## Included

- Responsive browser interface with light/dark themes; no frontend build or CDN dependency.
- Administrator and member accounts, Argon2 passwords, HTTP-only sessions, CSRF checks, login throttling.
- Private knowledge bases and configurable assistants for each user.
- Local GGUF loading/unloading, CPU/GPU/context controls through llama-cpp-python.
- Streaming responses, stop generation, persistent history, rename, delete, and JSON export.
- Document answers with source passages, document names, and physical PDF page numbers.
- PDF ingestion, optional OCR, a persistent processing queue, progress, errors, and reindexing.
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
4. Copy a compatible **instruction/chat GGUF model** to the host's **models** folder.
5. Open **Models → Refresh files**, select it, and click **Load model**.
6. Start with **4096 context**, **4 CPU threads**, **0 GPU layers**, and **512 response tokens**. Lower settings if memory is limited.
7. Open **Knowledge**, create a knowledge base, and upload a PDF.
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

## GGUF models and hardware

The operator supplies model files. Choose a model supported by the installed inference version and check its own licence and chat-template requirements.

- Only local GGUF files inside NELSON_MODELS_DIR appear in the picker.
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

## PDF knowledge

Each user owns their assistants, knowledge bases, and conversations. This release provides **private user libraries**, without cross-user sharing or team workspace permissions. Administrators manage accounts and installation settings. Administrators/server operators can access full backups and database files.

Processing:
1. Validate/limit PDF bytes and save the original and checksum in SQLite.
2. Claim the durable queue entry and start a time-limited PDF subprocess.
3. Extract text by page and attempt OCR on pages containing very little text.
4. Divide text into bounded overlapping passages and generate optional embeddings.
5. Publish all passages in one transaction after indexing succeeds.

Defaults: **25 MB/PDF, 250 MB original PDFs/user, 300 pages/PDF, 10,000 passages/knowledge base, 600 seconds/indexing job**. Text, embeddings, and chats consume additional disk space beyond the PDF quota.

Document states are queued, processing, ready, and failed. Interrupted jobs are requeued when the worker restarts. Reindexing hides old passages until ready. Deleting a document removes its PDF and searchable passages; historical conversation excerpts remain.

OCR requires requirements-ocr.txt, Tesseract, and the selected language pack. Docker includes English. Set NELSON_OCR_LANGUAGE after installing another language pack. Blank/mixed-layout PDFs may need manual preparation. Unlock password-protected PDFs before uploading.

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

Document mode requires a self-contained question. Previous conversation turns are not used as evidence; restate the subject in follow-up questions.

Without passages, the app answers without calling the model. With passages, instructions require evidence-based answers, acknowledged gaps, and source identifiers. Unknown labels are flagged, never linked. Source panels use retrieved metadata rather than model-generated URLs.

**Citations do not guarantee correctness.** Relevance thresholds and instructions cannot guarantee grounded answers. PDF text is untrusted context, but prompting alone cannot fully prevent prompt injection. The model has no shell, browsing, or file-writing tools.

## Backup and migration

Use **Settings & backup → Download backup** as administrator. The archive contains a consistent SQLite snapshot, original PDFs, embeddings, account hashes, conversations, and a checksum manifest. Model weights are excluded.

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
| app/worker.py | Persistent queue and subprocess timeouts |
| app/maintenance.py | Snapshot and validated restore |
| app/cli.py | Start, setup, backup, restore, password recovery |
| app/static/ | HTML/CSS/JavaScript application |
| tests/ | API, isolation, retrieval, streaming, recovery tests |
| deploy/ | Proxy and service examples |

Implementation uses FastAPI, SQLite directly, and a self-contained JavaScript frontend. React, npm, Redis, a separate vector database, and cloud AI keys are not required.

## Development and verification

API documentation is at /docs. Mutations require a session cookie, X-Nelson-Client: web, and the X-CSRF-Token returned at login. PDF uploads use application/pdf bytes and a URL-encoded X-Filename header.

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
