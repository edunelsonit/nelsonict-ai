# Target-machine acceptance checklist

## Actual model
- Load the intended GGUF and confirm streaming with a general question.
- Restart and confirm saved configuration reloads.
- Stop a long response and verify partial text is marked cancelled.
- Attempt a second response and verify a busy message.
- Measure memory/latency with your context, CPU, and GPU settings.
- Try a long question and confirm a bounded response or readable context error.

## Documents
- Upload a text PDF and verify a factual answer against its sources.
- Compare physical PDF page numbers with displayed citations.
- Test a scanned PDF with the intended OCR language.
- Ask an unsupported question and examine whether missing evidence is acknowledged.
- Reindex and ensure old passages are unavailable during processing.
- Delete a PDF and check that future retrieval cannot use it; historical excerpts remain.
- Restart the worker during indexing and verify the job retries.

## Semantic search
- Enable the actual local embedding model, restart, and reindex.
- Ask a paraphrased question without exact source wording.
- Change models, restart, and verify a reindex error.
- Reindex and verify normal retrieval.

## Access and recovery
- Check two member accounts cannot access each other's documents, chats, or assistants.
- Disable an account and verify its existing session fails.
- Restore a backup into a fresh directory/volume and verify PDFs/chats/accounts.
- Verify restored sessions are revoked and model settings need review.
- Test LAN/HTTPS uploads and streaming from another device.
- Inspect light/dark layouts at desktop and mobile sizes.
- Measure peak RAM with simultaneous indexing and generation.

Automated tests simulate generation and do not establish hardware compatibility, model quality, OCR accuracy, or production capacity.

## Version 1.1
- Run Setup wizard and review detected hardware/dependencies before loading a model.
- Import a GGUF with a publisher checksum and confirm a mismatch is rejected.
- Save a CPU profile, change the form, reapply the profile, and load.
- Upload DOCX/TXT/MD/CSV/XLSX samples and verify paragraph/line/sheet references.
- Test follow-up questions and full summary/comparison with your actual model.
- Click PDF citations and check displayed pages.
- Grant reader then editor access; verify edit controls and backend permissions.
- Revoke sharing and confirm new retrieval/downloads stop; historical chat excerpts remain.
- Upgrade a backup of the v1 database and compare document/chat counts.
