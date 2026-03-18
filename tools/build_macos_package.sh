#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_EXE="${PYTHON_EXE:-.venv/bin/python}"
if [[ ! -x "$PYTHON_EXE" ]]; then
  echo "Python nao encontrado em '$PYTHON_EXE'." >&2
  exit 1
fi

APP_NAME="CFO-Sync"
DIST_APP="dist/${APP_NAME}.app"
INSTALLER_DIR="dist/installer"
DMG_PATH="${INSTALLER_DIR}/CFO-Sync-macOS.dmg"

mkdir -p "$INSTALLER_DIR"

echo "==> Instalando dependencias de build..."
"$PYTHON_EXE" -m pip install --upgrade pip
"$PYTHON_EXE" -m pip install -r requirements.txt pyinstaller

echo "==> Gerando app macOS com PyInstaller..."
"$PYTHON_EXE" -m PyInstaller \
  launcher_desktop.py \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --paths src \
  --collect-data cfo_sync \
  --add-data "sounds:sounds" \
  --add-data "templates:templates" \
  --osx-bundle-identifier "com.cfosync.desktop"

if [[ ! -d "$DIST_APP" ]]; then
  echo "Build falhou, app nao encontrado: $DIST_APP" >&2
  exit 1
fi

echo "==> Gerando DMG..."
rm -f "$DMG_PATH"
hdiutil create -volname "CFO Sync" -srcfolder "$DIST_APP" -ov -format UDZO "$DMG_PATH"

echo "==> Pacote pronto:"
echo "    $DMG_PATH"
