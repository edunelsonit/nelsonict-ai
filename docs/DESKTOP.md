# Windows and Ubuntu desktop packages

Nelsonict AI's desktop launcher starts the API and document worker, opens the browser workspace, stops/restarts the service, enables automatic startup at user sign-in, and opens the official release page for updates. Closing the launcher leaves the background service running; choose **Stop application** to stop it.

Packages contain the Python application and native inference dependencies. GGUF weights and semantic embedding models are not bundled. OCR uses the bundled Python dependencies plus an external Tesseract installation; the Ubuntu package recommends Tesseract packages. Windows users must install Tesseract separately and place it on PATH if they need scanned-PDF OCR.

## Build the installers

Build on each target OS. PyInstaller does not produce a Windows executable from a Linux build. Linux bundles depend on the build host's glibc baseline; the installer workflow targets Ubuntu 22.04 x64. See [PyInstaller's platform guidance](https://pyinstaller.org/en/latest/usage.html).

The **Desktop installers** GitHub Actions workflow runs manually, on relevant changes to `main`, or on a `v*` tag and uploads `.exe` and `.deb` workflow artifacts. It does not automatically publish a release. Download binaries only from a successful build whose source and validation you have reviewed.

### Ubuntu x64

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev python3-tk build-essential cmake libgomp1 libgl1 libx11-6 libxext6 libxrender1 libfontconfig1 libfreetype6
python3 -m venv .venv
source .venv/bin/activate
CC=gcc CXX=g++ CMAKE_ARGS='-DGGML_NATIVE=OFF' CMAKE_BUILD_PARALLEL_LEVEL=2 pip install -r requirements-packaging.txt
python packaging/build.py
bash packaging/linux/build-deb.sh
sudo apt install ./dist/nelsonict-ai_1.2.0_amd64.deb
```

Open **Nelsonict AI** from the applications menu. The binary is installed under `/opt/nelsonict-ai`, and its menu entry uses the supplied logo. Enable automatic startup in the launcher to create a per-user `~/.config/autostart/nelsonict-ai.desktop` entry. This is graphical-session sign-in startup, not a machine-wide boot service. Use the existing systemd deployment for unattended server boot.

### Windows x64

Use Python 3.12 x64, a compatible C/C++ toolchain and CMake for the native dependency, and Inno Setup 6. A compatible inference wheel can be installed instead of compiling where available.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
$env:CMAKE_ARGS = '-DGGML_NATIVE=OFF'
$env:CMAKE_BUILD_PARALLEL_LEVEL = '2'
pip install -r requirements-packaging.txt
python packaging/build.py
& 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe' packaging/windows/installer.iss
```

The installer appears in `dist/installers/`. It installs per-user under `%LOCALAPPDATA%\Programs\NelsonictAI`, creates a Start Menu shortcut, and offers optional desktop and sign-in startup tasks. The launcher also controls the same per-user startup registry value. No administrator elevation is requested by the installer. See the [Inno Setup architecture settings](https://jrsoftware.org/ishelp/topic_setup_architecturesallowed.htm) for the x64-compatible target.

The current frozen build uses console mode so service diagnostics and shutdown behaviour remain available. It is not a signed, silent system service. Signing certificates and Windows trust reputation are not provided by this source project.

## First launch and storage

The launcher creates a per-user directory:

| Platform | Default application data root |
|---|---|
| Windows | `%LOCALAPPDATA%\NelsonictAI` |
| Ubuntu | `~/.local/share/NelsonictAI` |

Inside it, `data` is the stable database/configuration bootstrap directory, `models` holds your GGUF files, and `desktop-service.log` captures startup output. The setup token is initially in `data/setup-token.txt`. Use **Copy first-run setup token** in the launcher, create your administrator in the browser and follow the setup wizard.

Existing source/native installations can be imported through the guided migration interface. A browser launched from a different computer cannot select a local path on that computer as the server's model directory: copy files to the actual AI server first.

## Updates and removal

**Check for updates** opens the repository's official release page. Updates are deliberately installed by the operator: download a matching installer from a published release or validated workflow, back up, stop the application, install the new package, then start and verify it. The launcher does not silently download or execute an update. Keep the old backup if a database migration is involved.

Program files and per-user data are separate, so reinstalling/upgrading preserves documents, accounts and model files. Before uninstalling, disable automatic startup and stop the application. Uninstall the Windows application normally or use `sudo apt remove nelsonict-ai` on Ubuntu. Private data remains in the per-user data directory for recovery; delete it separately only when intended.

## Validation boundary

Source and API/DOM tests do not certify native installer behaviour. Check each generated package on a clean target machine: install, launch, load a real compatible GGUF, index a document, stop/restart, enable/disable sign-in startup, upgrade and uninstall. Linux package compatibility depends on the build machine's glibc baseline. Windows installer compilation, signing and installed behaviour require a Windows environment. See [ACCEPTANCE.md](ACCEPTANCE.md).

Local v1.2 verification built a Linux `.deb` on Ubuntu 24.04 with glibc 2.39. Its frozen executable passed HTTP startup, bundled frontend, setup/login, native inference import, real text-document indexing through the worker subprocess, and shutdown checks. That local package requires glibc 2.39 or newer; it is not the Ubuntu 22.04 workflow build. Graphical launcher rendering, Windows installer execution and real GGUF generation remain target-machine acceptance checks.
