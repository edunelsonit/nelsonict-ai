# API guide

The running instance serves an offline reference at `/docs` and its exact OpenAPI schema at `/openapi.json`. Use those schemas for field definitions. This guide explains authentication, upload/stream behaviour and the feature groups in version 1.2.

## Authentication and request headers

`POST /api/login` accepts a JSON body with `username` and `password`. Send `X-Nelson-Client: web`. On success, retain the `nelson_session` cookie and the returned `csrf` value. Cookies alone are insufficient for authenticated mutations.

| Request type | Required credentials/headers |
|---|---|
| Authenticated read | Session cookie. |
| Authenticated mutation | Session cookie, `X-Nelson-Client: web`, and `X-CSRF-Token` matching the session. |
| Setup/login | Application client header; setup also needs the local setup token. |
| Anonymous public mutation | Application client header; no workspace session or CSRF token. |

Browser origins are checked on mutations. Do not try to work around rejected origin/host checks by disabling the protections. Correct the reverse proxy, configured hostnames or calling origin. There are no API keys, bearer-token grants or general cross-origin CORS configuration in this implementation.

The public iframe sends requests from its own AI-server origin. Its embedding site's origin does not become the API request origin.

## Private API groups

`{id}` below is a placeholder; the OpenAPI schema uses the implementation's parameter names.

| Area | Endpoints |
|---|---|
| Health/setup | `GET /api/health`, `GET/POST /api/setup` |
| Session | `POST /api/login`, `GET /api/me`, `POST /api/logout` |
| Accounts | `GET/POST /api/users`, `POST /api/users/{id}/enable`, `POST /api/users/{id}/disable` |
| Wizard/model | `GET /api/system/check`, `POST /api/system/model-test`, `POST /api/system/complete`, `GET /api/models`, `POST /api/models/load`, `POST /api/models/unload` |
| Model files/profiles | `POST /api/models/import`, `GET /api/models/inspect`, `GET/POST /api/model-profiles`, `DELETE /api/model-profiles/{id}` |
| Knowledge | `GET/POST /api/knowledge`, `DELETE /api/knowledge/{id}`, `GET/POST /api/knowledge/{id}/documents` |
| Documents | `GET /api/documents/{id}/download`, `GET /api/documents/{id}/preview`, `POST /api/documents/{id}/reindex`, `DELETE /api/documents/{id}` |
| Membership | `GET/POST /api/knowledge/{id}/members`, `DELETE /api/knowledge/{id}/members/{member_id}` |
| Assistants | `GET/POST /api/assistants`, `PUT/DELETE /api/assistants/{id}` |
| Conversations | `GET/POST /api/conversations`, `PUT/DELETE /api/conversations/{id}`, `GET /api/conversations/{id}/messages`, `GET /api/conversations/{id}/export` |
| Chat | `POST /api/conversations/{id}/chat`, `POST /api/conversations/{id}/stop` |
| Queue | `GET /api/queue`, `POST /api/queue/pause`, `POST /api/queue/cancel` |
| Feedback | `POST/DELETE /api/messages/{id}/feedback`, `GET /api/feedback` |
| Evaluation questions | `GET/POST /api/evaluation/questions`, `PUT/DELETE /api/evaluation/questions/{id}` |
| Evaluation runs | `GET/POST /api/evaluation/runs`, `GET /api/evaluation/runs/{id}`, `POST /api/evaluation/runs/{id}/cancel`, `POST /api/evaluation/runs/{id}/review` |
| Recovery | `GET /api/backup`, `GET /api/migration/settings`, `POST /api/migration/stage`, `POST /api/migration/{id}/activate`, `DELETE /api/migration/{id}`, `POST /api/migration/restart` |
| Public administration | `GET/POST /api/public-sites`, `PUT/DELETE /api/public-sites/{id}` |
| Status | `GET /api/status` |

Accounts, model controls, setup wizard, backup/migration, feedback reports, queue pause and public administration require administrator access. Queue list/cancel is limited to the caller's tickets unless the caller is an administrator. Knowledge membership/deletion uses owner permissions; uploads/reindex allow owners and editors. Personal conversations, assistants and evaluations require ownership.

## Upload conventions

Document and GGUF uploads use **raw bytes**, not multipart form data:

- Documents: `POST /api/knowledge/{id}/documents`, URL-encoded `X-Filename`, appropriate content type or `application/octet-stream`.
- GGUF: `POST /api/models/import`, URL-encoded `X-Filename`, and optional expected 64-character hexadecimal `X-SHA256`.
- Backup staging: `POST /api/migration/stage`, raw ZIP bytes. The archive is validated and restored in an isolated directory before the response returns.

A document upload returns HTTP 202 and a queued document ID. Poll the collection's documents endpoint until Ready or Failed; upload success alone does not mean indexing succeeded. A model import returns after validation/installation; it does not load the model. Backup staging returns a stage ID, restored data path and record counts; it does not activate that database.

## Chat request and stream

Create a conversation first, then send its chat request:

```json
{
  "content": "What requirements are described in these documents?",
  "mode": "documents",
  "kb_id": 1,
  "task": "question",
  "document_ids": [1, 2]
}
```

Use `mode: "general"` with `task: "question"` for general chat. `task: "summary"` requires selected documents; `task: "compare"` requires at least two distinct ready documents. Document tasks accept at most eight selected IDs. All IDs must be accessible in the selected collection.

The response is Server-Sent Events over a **POST** request. Browser clients should use streaming `fetch`, since native `EventSource` uses GET. Each event is a JSON object in an SSE `data:` field. Ignore heartbeat comments.

| Event type | Client action |
|---|---|
| `queue` | Show the waiting `position` and `message`. |
| `progress` | Display the task's progress message. |
| `sources` | Display the supplied `sources` array as evidence. |
| `token` | Append `text` to the answer. |
| `error` | Display `message`; a stream can fail after HTTP 200. |
| `done` | End reading and inspect the final private-chat `status` when present. |

Handle transport disconnects and incomplete streams; do not assume an HTTP 200 means a completed answer. Use the stop endpoint to cancel your conversation's ticket. A restarted server does not resume the in-memory stream.

### Minimal Python client

This example uses `httpx`, already included in the project dependencies. It prompts privately for a password and streams a general answer. Run it only against an installation where you have an account and an administrator has loaded a model.

```python
import getpass
import json
import httpx

base_url = input("Server URL [http://127.0.0.1:8000]: ").strip() or "http://127.0.0.1:8000"
with httpx.Client(base_url=base_url, timeout=30) as client:
    client.headers["X-Nelson-Client"] = "web"
    login = client.post("/api/login", json={
        "username": input("Username: "),
        "password": getpass.getpass("Password: "),
    })
    login.raise_for_status()
    client.headers["X-CSRF-Token"] = login.json()["csrf"]
    created = client.post("/api/conversations", json={"title": "API example"})
    created.raise_for_status()
    conversation_id = created.json()["id"]
    with client.stream(
        "POST", f"/api/conversations/{conversation_id}/chat",
        json={"content": "Explain local AI briefly.", "mode": "general", "task": "question"},
        timeout=httpx.Timeout(30, read=660),
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            if event["type"] == "token":
                print(event["text"], end="", flush=True)
            elif event["type"] in ("queue", "progress", "error"):
                print("\n" + event.get("message", ""))
            elif event["type"] == "done":
                print("\nStatus:", event.get("status", "finished"))
                break
    client.post("/api/logout").raise_for_status()
```

The stream parser above matches the server's current single-line JSON event format. A general-purpose SSE client should also handle multi-line data fields.

## Queue, feedback and evaluation bodies

Queue pause accepts `{"paused": true}`. Queue cancellation accepts `{"key": "chat:123"}` using a key from the queue response. Never infer that knowing another user's key grants cancellation permission.

Feedback accepts `{"rating": "incorrect", "note": "The stated deadline differs from the source."}` or rating `helpful`. An API client should obtain the same explicit user agreement to share the answer/source excerpts with administrators that the browser interface requests.

An evaluation question contains `kb_id`, `question` and `expected`. A new run contains `question_ids` with 1–20 entries. Poll its ID for `queued`, `running`, `complete`, `cancelled`, `failed` or `interrupted` state. A result review contains `question_id`, `verdict` (`pass`, `fail`, `unreviewed`) and an optional `note`. Reviews are accepted after the run stops, not while queued/running.

## Anonymous public API

`GET /widget/{site_id}` serves the iframe interface for an enabled public assistant. `POST /api/public/{site_id}/chat` accepts `{"question": "What training is available?"}` with at most 2,000 characters.

The stream begins with a `request` event containing an opaque cancellation token. Cancel through `POST /api/public/{site_id}/cancel/{token}`. Do not expose that token to unrelated visitors. Public source objects contain approved names, locations and excerpts; they do not provide private document download endpoints. Public requests do not create saved conversations.

A public endpoint is anonymous and may be called directly. Its HTTPS origin list controls framing, not authentication. The default public admission limit is shared across sites, with a separate site/IP rate limit. See [website integration](WEBSITE.md).

## Common response codes

| Code | Typical meaning |
|---|---|
| 400 / 422 | Invalid settings, unsupported input, or schema validation failure. |
| 401 | No valid session. |
| 403 | Insufficient role, failed CSRF/client/origin check, or forbidden operation. |
| 404 | Missing or inaccessible item; public assistant disabled/unavailable. |
| 409 | Model conflict, duplicate item, paused/full private queue, or incompatible operation state. |
| 413 | Configured upload/storage limit exceeded. |
| 429 | Rate limit or public queue admission rejected. |
| 507 | Insufficient staging space. |

Errors raised during a stream arrive as events rather than a replacement HTTP status. Keep sensitive response bodies, session values and document excerpts out of diagnostic logs.

## Model downloads (administrator)

Use `POST /api/models/downloads` with `url`, optional `filename` and optional `sha256`; poll `GET /api/models/downloads` and cancel with `POST /api/models/downloads/{id}/cancel`. See [model downloads](MODEL-DOWNLOADS.md) for statuses and validation.
