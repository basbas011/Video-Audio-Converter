#!/usr/bin/env bash
# Bouwt dist/Video-Audio-Converter-Setup.exe op Linux (gebruikt door GitHub Actions).
# Gebruik: scripts/build_installer.sh 2.3.0
# Vereist: python3.12, pip, makensis (NSIS), curl, tar
set -euo pipefail

VERSION="${1:?Geef een versie op, bijv. 2.3.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/build"
STAGE="$WORK/stage"
PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20241206/cpython-3.12.8+20241206-x86_64-pc-windows-msvc-install_only.tar.gz"
PYTHON="${PYTHON:-python3.12}"

echo "==> Versie $VERSION bouwen"
rm -rf "$WORK" "$ROOT/dist"
mkdir -p "$WORK/wheels" "$STAGE/app" "$ROOT/dist"

echo "==> Windows-Python ophalen"
curl -sSL -o "$WORK/python.tar.gz" "$PY_URL"
tar -xzf "$WORK/python.tar.gz" -C "$STAGE"

echo "==> Overbodige onderdelen verwijderen"
cd "$STAGE/python"
find . -name "*.pdb" -delete
rm -rf include libs Scripts Lib/test Lib/idlelib Lib/turtledemo Lib/ensurepip Lib/lib2to3 \
       Lib/tkinter/test Lib/site-packages/pip* DLLs/_test* tcl/nmake
find . -name "__pycache__" -type d -prune -exec rm -rf {} +

echo "==> Bibliotheken toevoegen"
"$PYTHON" -m pip download -q --only-binary=:all: --platform win_amd64 --python-version 3.12 \
    --no-deps -d "$WORK/wheels" "customtkinter==5.2.2" "darkdetect==0.8.0" packaging
for whl in "$WORK"/wheels/*.whl; do
    "$PYTHON" -m zipfile -e "$whl" Lib/site-packages/
done

echo "==> Programma toevoegen"
cp "$ROOT/src/video_audio_converter.py" "$ROOT/src/icon.ico" "$STAGE/app/"
sed -i "s/^APP_VERSION = \".*\"/APP_VERSION = \"$VERSION\"/" "$STAGE/app/video_audio_converter.py"
grep -q "^APP_VERSION = \"$VERSION\"" "$STAGE/app/video_audio_converter.py"

echo "==> Voorcompileren (snellere start)"
"$PYTHON" -m compileall -q -j0 "$STAGE/python/Lib" >/dev/null || true

echo "==> Installer bouwen"
cd "$ROOT/installer"
makensis -V2 -DVERSION="$VERSION" -DSTAGE="$STAGE" -DOUTFILE="$ROOT/dist/Video-Audio-Converter-Setup.exe" installer.nsi
ls -la "$ROOT/dist"
