# Download GGUF models

Administrators can download public model files directly onto the Nelsonict AI server. Open **Models → Download a GGUF model**. Internet access is needed on the server during the download; inference continues locally once weights are installed.

## Hugging Face

1. Choose **Hugging Face repository**.
2. Enter the repository ID, such as `owner/model-GGUF`.
3. Copy the exact GGUF file path from the repository's file listing, including any subdirectory. Select a quantization that fits your RAM/VRAM and has a licence suitable for your use.
4. Leave revision as `main`, or enter a branch, tag or commit. A commit plus a publisher-provided checksum is preferable for reproducible installations.
5. Optionally enter a local filename and the publisher's expected SHA-256.
6. Start the download. Watch progress or cancel it in Models.
7. When complete, click **Select in model form**, review context/CPU/GPU settings, then **Load model**.

The form builds a Hugging Face `resolve` URL. Hugging Face file-page links containing `/blob/` also work through the direct URL option: they are converted to `/resolve/`. See the upstream [download documentation](https://huggingface.co/docs/hub/models-downloading).

## Other repositories

Choose **Direct HTTPS file URL** and paste a public raw-file, release-asset or download link. HTTPS port 443 is required. Redirects to public HTTPS CDN hosts are supported. An HTML repository page, Git LFS pointer, ZIP archive or non-GGUF file is rejected.

If the URL does not end in the desired filename, provide a local filename ending in `.gguf`. Existing models are never overwritten. Split GGUF weights are not assembled by this downloader; use a single-file model or prepare a compatible model manually.

Private and gated repositories requiring credentials are not supported by this form. Download them separately after obtaining access and accepting their terms, then use **Import a GGUF file**. Never embed credentials in a URL.

## Progress, validation and limits

- Only administrators can start, list or cancel downloads. One download can run at a time while other API controls remain available.
- Bytes received and the declared total are shown. A server without a declared total has indeterminate progress.
- The existing `NELSON_MAX_MODEL_MB` setting applies, including when the repository omits its file size. Free space is checked with a 64 MiB reserve.
- Downloads are staged in a temporary file, hashed and inspected for supported GGUF metadata before atomic installation. Metadata inspection does not fully validate tensor contents or prove model compatibility; load and test the model afterwards.
- Providing an expected SHA-256 requires an exact match. Without one, the calculated hash is displayed, but publisher authenticity has not been verified.
- Every redirect's destination is checked. Local, private and reserved addresses are blocked, DNS results are pinned for the connection, and TLS certificates are verified.
- Requests use direct connections, without environment HTTP proxies, authentication tokens or cookies. Allow the repository and its CDN hosts through your server's outbound firewall.
- Cancellation is cooperative. A stalled network operation can take about 30 seconds to time out. There is a six-hour download deadline, checked between network operations.
- Downloads do not automatically load weights or change the active model.

## Restart and troubleshooting

The latest 20 jobs are kept in memory. Jobs and progress do not survive application restart, and partial downloads cannot resume. Cancellation and ordinary failures remove partial files. After a forced process exit, stop the application before removing leftover `.download-*.part` files from the configured models directory.

For HTTP 401/403, check whether the file is gated or a signed link expired. For invalid GGUF, use the raw file link. For size or disk errors, review the model-size setting and server storage. Models downloaded inside Docker are stored in its configured models volume.

The automated download tests use generated GGUF metadata and simulated network responses. A live multi-gigabyte Hugging Face download and real-model inference were not verified in this implementation environment.

## API

All endpoints require an administrator session; POST requests also require the normal CSRF header.

| Endpoint | Result |
|---|---|
| `POST /api/models/downloads` | Accepts `url`, optional `filename` and optional `sha256`; returns HTTP 202 with job `id`. |
| `GET /api/models/downloads` | Recent jobs with status, byte counts, errors and completed checksums; source query tokens are not returned. |
| `POST /api/models/downloads/{id}/cancel` | Requests cancellation and returns current status. |

Statuses are `downloading`, `validating`, `cancelling`, `complete`, `cancelled` and `failed`. HTTP 409 on creation means another download is running or the destination filename already exists.
