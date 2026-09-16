#!/usr/bin/env bash
set -euo pipefail
package_dir="dist/deb-root"
libc_version="$(getconf GNU_LIBC_VERSION | awk '{print $2}')"
mkdir -p "$package_dir/DEBIAN" "$package_dir/opt/nelsonict-ai" "$package_dir/usr/share/applications" "$package_dir/usr/share/icons/hicolor/scalable/apps"
cp -a dist/nelsonict-ai/. "$package_dir/opt/nelsonict-ai/"
cp app/static/logo.svg "$package_dir/usr/share/icons/hicolor/scalable/apps/nelsonict-ai.svg"
cat > "$package_dir/DEBIAN/control" <<EOF
Package: nelsonict-ai
Version: 1.2.0
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Nelsonict Services Limited
Depends: libc6 (>= ${libc_version}), libgomp1, libgl1, libx11-6, libxext6, libxrender1, libfontconfig1, libfreetype6
Recommends: tesseract-ocr, tesseract-ocr-eng
Description: Local GGUF chatbot and document knowledge workspace
 Includes a desktop launcher, local API and document worker.
 Model weights are supplied separately. User data is retained on upgrade.
EOF
cat > "$package_dir/usr/share/applications/nelsonict-ai.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Nelsonict AI
Comment=Local chatbot and document knowledge
Exec=/opt/nelsonict-ai/nelsonict-ai
Icon=nelsonict-ai
Terminal=false
Categories=Office;Education;
EOF
chmod 755 "$package_dir/opt/nelsonict-ai/nelsonict-ai"
mkdir -p "$package_dir/usr/share/doc/nelsonict-ai"
cp LICENSE "$package_dir/usr/share/doc/nelsonict-ai/copyright"
dpkg-deb --root-owner-group --build "$package_dir" dist/nelsonict-ai_1.2.0_amd64.deb
