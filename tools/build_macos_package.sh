#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_EXE="${PYTHON_EXE:-.venv/bin/python}"
if [[ ! -x "$PYTHON_EXE" ]]; then
  echo "Python nao encontrado em '$PYTHON_EXE'." >&2
  exit 1
fi

APP_VERSION="$(
  awk -F'"' '
    /^[[:space:]]*version[[:space:]]*=[[:space:]]*"/ {
      print $2
      exit
    }
  ' pyproject.toml
)"
if [[ -z "$APP_VERSION" ]]; then
  echo "Nao foi possivel ler a versao do pyproject.toml." >&2
  exit 1
fi
if [[ ! "$APP_VERSION" =~ ^[0-9]+(\.[0-9]+){2}([.-][0-9A-Za-z]+)?$ ]]; then
  echo "Versao invalida lida do pyproject.toml: '$APP_VERSION'" >&2
  exit 1
fi

APP_NAME="CFO-Sync"
DIST_APP="dist/${APP_NAME}.app"
INSTALLER_DIR="dist/installer"
DMG_PATH="${INSTALLER_DIR}/CFO-Sync-macOS.dmg"
DMG_VERSIONED_PATH="${INSTALLER_DIR}/CFO-Sync-macOS-v${APP_VERSION}.dmg"
ZIP_PATH="${INSTALLER_DIR}/CFO-Sync-macOS.zip"

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

echo "==> Gerando zip portavel macOS..."
rm -f "$ZIP_PATH"
ditto -c -k --sequesterRsrc --keepParent "$DIST_APP" "$ZIP_PATH"

echo "==> Gerando DMG..."
rm -f "$DMG_PATH" "$DMG_VERSIONED_PATH"
hdiutil create -volname "CFO Sync" -srcfolder "$DIST_APP" -ov -format UDZO "$DMG_PATH"
cp "$DMG_PATH" "$DMG_VERSIONED_PATH"

echo "==> Pacotes prontos:"
echo "    $ZIP_PATH"
echo "    $DMG_PATH"
echo "    $DMG_VERSIONED_PATH"
