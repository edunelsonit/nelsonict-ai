# Embed Nelsonict AI on nelsonict.com.ng

The website assistant answers only from explicitly approved documents in a separate collection. It runs on your Nelsonict AI server. No GGUF weights or private workspace credentials are sent to the website visitor.

## Prepare the server

Deploy Nelsonict AI at an HTTPS address such as `https://ai.nelsonict.com.ng`, configure DNS and a reverse proxy, and load a model. The example subdomain is a deployment suggestion, not an address provisioned by this repository. Add your actual AI hostname to `NELSON_ALLOWED_HOSTS` and set secure cookies for the administrator workspace.

The main website can stay on shared hosting; the AI server still needs long-running Python/native inference and adequate memory. See [DEPLOYMENT.md](DEPLOYMENT.md). Preserve streaming responses at the proxy. Configure trusted forwarded addresses correctly if you need per-visitor rather than shared proxy-IP rate limits.

## Approve public information

1. Sign in as administrator and open **Operations & website**.
2. Create a public assistant and list exact permitted HTTPS origins, normally `https://nelsonict.com.ng` and `https://www.nelsonict.com.ng`.
3. Open its newly created **Public · …** knowledge collection. This is separate from existing private collections.
4. Upload only material intended for public use: approved service descriptions, opening hours, training details, policies or contact information. Wait for Ready.
5. Return to the public assistant, select ready documents, acknowledge that their contents and excerpts will be anonymously public, and enable the assistant.
6. Save publication and copy the generated iframe code.

New uploads are not automatically approved. The approval list ties document IDs to original-file checksums; a changed or non-ready document is excluded until the owner reviews publication again. Changes to publication cancel that site's outstanding queued/running requests cooperatively. Restoring a backup disables public assistants until explicit review and re-enablement.

## Add the widget to the website

Paste the generated snippet into a custom HTML block, template or page on the main website. Example only—replace both host and ID with your actual values:

```html
<iframe
  src="https://ai.nelsonict.com.ng/widget/1"
  title="Nelsonict AI"
  width="100%"
  height="620"
  loading="lazy"
  referrerpolicy="strict-origin-when-cross-origin">
</iframe>
```

Your main site's Content Security Policy must permit the AI host in `frame-src`. The widget response sets `frame-ancestors` to the configured origins. The private workspace keeps framing disabled. Cross-origin API access and private login cookies are not needed: the iframe serves its own same-origin assets and sends anonymous requests with cookies omitted.

The origin list controls browser embedding, not authentication or secrecy. The public endpoint can be called directly by anyone. Do not publish personal information, confidential prices, internal procedures, credentials or restricted documents unless they are intentionally public.

## Visitor experience and data

Visitors submit a question, see the waiting position when the model is occupied, receive a streamed answer, inspect approved source excerpts and cancel their request. No sign-in is required. Public answers do not offer original-file download links. Requests are stateless; there is no anonymous conversation history or follow-up memory in this version.

Public questions and answers are not saved as conversations by this implementation. Temporary request data exists in process memory, rate-limit records are stored in SQLite, and your proxy/server logging policy still applies. The widget advises visitors not to enter private information. AI answers require verification even when citations are present.

Public traffic shares the queue with private chats and evaluations. Public requests collectively use the default two-request admission limit and each site/IP is limited to ten requests per five minutes. A reverse proxy/CDN may add stronger abuse controls. A website outage does not require exposing the private collection as a fallback: the widget returns an unavailable or insufficient-evidence response.

## Disable or remove

Clear **Enable public assistant** and save to stop new public access. Removing a public assistant removes its publication settings; its underlying collection remains private in Knowledge for review or deletion. Information already displayed to visitors cannot be retracted.

## Integration check

- Open the widget URL directly and ask about an approved document.
- Ask for a fact that exists only in a private or unapproved document; it must not appear in the source list.
- Load your real website and verify the iframe is permitted by both sites' CSP settings.
- Test queue waiting and Cancel with an occupied model.
- Disable publication and confirm new public requests fail.

The repository supplies the working integration and snippet generator. Website CMS/server changes and DNS provisioning must be performed in the environment where `nelsonict.com.ng` is managed.
