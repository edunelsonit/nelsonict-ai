# Nelsonict AI documentation

Documentation for the version 1.2 implementation. Start with the guide for your role, then use the feature-specific instructions when needed.

| What you want to do | Guide |
|---|---|
| Install the application and load your first model | [Project README](../README.md) |
| Chat, upload documents, share knowledge and check answers | [User guide](USER-GUIDE.md) |
| Manage accounts, the queue, models, backups and recovery | [Administrator guide](ADMIN-GUIDE.md) |
| Download GGUF weights from Hugging Face or a public repository | [Model downloads](MODEL-DOWNLOADS.md) |
| Understand the runtime, database and trust boundaries | [Architecture](ARCHITECTURE.md) |
| Integrate a client or inspect API conventions | [API guide](API.md) |
| Deploy on LAN, HTTPS, Docker or systemd | [Deployment](DEPLOYMENT.md) |
| Upgrade an older installation and use options 6–10 | [Version 1.2 guide](UPGRADE-1.2.md) |
| Build/install Windows or Ubuntu packages | [Desktop guide](DESKTOP.md) |
| Embed approved public information on nelsonict.com.ng | [Website guide](WEBSITE.md) |
| Verify a target machine before operational use | [Acceptance checklist](ACCEPTANCE.md) |
| Read the historical options 1–5 upgrade notes | [Version 1.1 guide](UPGRADE-1.1.md) |

## Choose your starting path

**First installation:** install → create administrator → run setup wizard → load/test GGUF → upload a document → wait for Ready → ask a document question → verify sources.

**Existing 1.0/1.1 installation:** back up → stop API and worker → update code/dependencies → restart and migrate schema → verify accounts, documents, model and queue. See the version 1.2 guide before running older code against any migrated database.

**Moving computers:** install on the target → create its initial administrator → upload a trusted backup through guided restore → review target settings → activate on restart → sign in with a restored account → load/test the target model.

**Website integration:** deploy the AI server over HTTPS → create a separate public collection → upload and review public documents → explicitly approve selected ready files → enable publication → add the generated iframe to the website.

## Version and verification status

The implementation is version **1.2.0**, with SQLite schema **3**. Archive format version **1** is unchanged. These version numbers describe different things.

Current verification passed 100 Python tests and extended frontend DOM smoke checks, including model downloads. Earlier verification also passed a Linux frozen-executable smoke test covering startup, authentication, native inference import, text indexing and shutdown. A local Ubuntu 24.04 x64 package was built. These checks do not establish graphical rendering, real GGUF/GPU generation, scanned-document accuracy, or live website deployment.

The Windows and Ubuntu GitHub installer jobs failed before running any steps at the last check, so no successful hosted package build is claimed. The local installer download transfer also failed. Package source and build instructions remain available. Version 1.2 was merged into main in [pull request #1](https://github.com/edunelsonit/nelsonict-ai/pull/1).

Uploading documents provides retrieval-augmented generation (RAG). It does not train or fine-tune model weights.
