# User guide

Nelsonict AI runs a language model on the computer or server hosting the application. Your browser provides the interface. Your administrator supplies accounts and loads a compatible GGUF model.

## Sign in and find your workspace

Open the address supplied by your administrator and sign in. Passwords contain 12–128 characters. If you cannot sign in, ask the administrator to check your account or use server-side password recovery; email password reset is not provided.

Use the navigation to open Chat, Knowledge, Assistants, Quality & evaluation, or Settings & backup. Administrators also see setup, model and operations controls. Choose light or dark appearance in Settings. Recent conversations appear in the sidebar.

## General chat

1. Choose **New conversation**.
2. Select an assistant, or leave **Nelsonict AI** selected.
3. Set **Answer mode → General chat**.
4. Enter your question and send it.
5. Read the streamed reply. Use **Stop** to cancel a waiting or active response.

General chat uses the model's learned knowledge, not your document collection. A model can be outdated or incorrect. It has no browsing, shell or file-writing tools in this application.

When another request occupies the model, your request waits in a queue and displays its position. A positive position includes requests ahead of yours, including the running request. A full or paused queue rejects new requests with an explanation. Native prompt evaluation may delay cancellation of a running reply.

You can rename a conversation, export its messages as JSON, or delete it. Stop a queued or active response before deleting its conversation. Interrupted replies retain their partial text and status. The current browser keeps you in the active conversation until its request finishes or is stopped.

## Create document knowledge

Open **Knowledge**, create a knowledge base, and upload supported documents. A knowledge base is a collection used to scope retrieval.

| Format | Preparation and source references |
|---|---|
| PDF | Use readable, unlocked files. Sources identify physical pages. Scanned pages need configured OCR. |
| DOCX | Main paragraphs and top-level tables are extracted. References identify source blocks. |
| TXT / Markdown | Save as UTF-8 text. References identify line ranges. |
| CSV | Save as UTF-8 with a useful header row. References identify rows. |
| XLSX | Save recalculated workbooks with cached cell values. References identify sheet/row locations. |

Convert legacy `.doc` and `.xls` files first. Excel formulas are not calculated by Nelsonict AI. Embedded images, complex Word structures and unusual layouts may need preparation. Uploading the same original file twice to the same collection is rejected by checksum.

Documents pass through **queued → processing → ready**, or **failed** with an error. A separate worker handles processing. Ready means indexing completed; it does not certify that extraction or OCR is accurate. Ask your administrator about files that remain queued or fail repeatedly.

Default limits are 25 MiB per original document, 250 MiB of originals per collection owner, 300 PDF pages and 10,000 passages per collection. Editor uploads count against the owner's quota. Extracted text, vectors and conversations consume additional storage.

## Ask document questions

1. Select **Document answers** in Chat.
2. Choose the knowledge base, or use your selected assistant's default collection.
3. Keep **Document task → Ask / follow up** selected.
4. Optionally select particular ready documents to narrow retrieval.
5. Ask a specific question and check the returned sources.

For example: “What are the registration requirements described in this document?” or “Which steps must be completed before installation?” A follow-up uses the last two user questions from the same collection as context and retrieves evidence again. Restate ambiguous names or pronouns when necessary.

Keyword search is available without an embedding model. If configured by the administrator, hybrid search also uses a local embedding model. Neither method guarantees relevant evidence. If no supporting passages are found, the application reports that instead of generating a document answer.

## Summarise or compare complete documents

Choose **Full summary** and select at least one ready document, or **Compare documents** and select at least two. Use Ctrl/Command in the document selector to choose multiple files on desktop.

These tasks process all indexed passages in the selected documents through multiple model calls. Progress is displayed during analysis. The default limit is 256 passages across at most eight selected documents, with a cooperative 15-minute analysis limit. Oversized requests fail explicitly; documents are not silently sampled. Select fewer documents if the analysis exceeds the limits.

A complete pass over extracted passages is not proof of a complete or accurate summary. Extraction can omit content and a model can misinterpret it. Verify important claims against the originals.

## Verify sources

Click a recognised citation or **Preview source**. PDF previews show a page image when the renderer is installed. Other formats show extracted source text and its location. Original downloads require current collection access.

A source panel is evidence to inspect, not a correctness certificate. Unknown citation labels are flagged rather than made into links. If access is revoked or the original is deleted, historical excerpts may remain in a saved chat while a new preview/download is denied.

## Share a knowledge base

Collections are private until their owner grants access to an existing active account through **Share this knowledge base**.

| Permission | Allowed actions |
|---|---|
| Reader | Ask questions, search, preview, download, and attach the collection to a personal assistant. |
| Editor | Reader actions plus upload and reindex. |
| Owner | Editor actions plus delete originals/collection and grant or revoke membership. |

Editors cannot delete or re-share a collection. Ask an administrator to create the recipient's account if it does not exist. Revocation blocks future access and cancels the affected user's queued/active private requests, but cannot retract excerpts or exported files already received.

Sharing knowledge does not share conversations or assistants. Public website publication is a separate administrator workflow with explicit document approval.

## Create a personal assistant

In **Assistants**, give the assistant a name, instructions and an optional accessible default collection. For example, an ICT tutor might explain concepts step by step and acknowledge missing evidence. Save it and select it when creating a conversation. The assistant does not get extra permissions beyond your account's collection access.

## Report an answer and evaluate changes

Use **Helpful** or **Flag incorrect** beneath a saved assistant answer. The interface asks whether to share the answer, its cited excerpts and your note with administrators. Cancel if you do not want that disclosure. **Remove feedback** removes the report; it does not retract anything an administrator has already seen.

In **Quality & evaluation**:

1. Choose a collection, write a question, and record the expected answer or key facts.
2. Save questions and select up to 20 for a run.
3. Run the set with the loaded local model. It uses the shared request queue.
4. Inspect each answer and its sources, then mark it pass or fail with a review note.
5. Export the run as JSON for a before/after comparison.

Expected-term coverage measures word overlap with your reference answer. It is not factual accuracy or confidence. Runs preserve their original question/reference snapshots when saved questions are later edited. Question sets and runs are personal; the latest 50 runs are listed in the interface.

## Common problems

| Problem | Next step |
|---|---|
| No model loaded | Ask the administrator to load and test a GGUF. |
| File stays queued | Ask the administrator to check the document worker. |
| Missing evidence | Check Ready status, selected collection/files and question wording. |
| Summary too large | Select fewer documents; ask the administrator about limits. |
| Source preview unavailable | Check current access and whether the original remains available. |
| Queue full or paused | Wait or cancel an earlier request; an administrator can inspect the queue. |
| Account disabled or expired session | Sign in again or contact the administrator. |

For recovery and operator actions, see the [administrator guide](ADMIN-GUIDE.md).
