#!/usr/bin/env bash
# Package Mnemo as a macOS app (dist/Mnemo.app) and, with --install, copy it to /Applications.
# The app bundles the Python brain (mnemo/) and uses the Python environment created by ./build.sh.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
[ -x .venv/bin/python ] || { echo "Run ./build.sh first"; exit 1; }

echo "==> Recording Python environment"
printf '{"python": "%s"}\n' "$ROOT/.venv/bin/python" > app/build-config.json

echo "==> Staging the brain"
rm -rf dist/brain && mkdir -p dist/brain
rsync -a --exclude '__pycache__' mnemo dist/brain/
mkdir -p dist/brain/website/public && cp website/public/firebase-config.js dist/brain/website/public/   # accounts config

echo "==> Packaging"
ARCH=$(uname -m); [ "$ARCH" = "x86_64" ] && ARCH=x64
(cd app && npx @electron/packager . Mnemo --platform=darwin --arch="$ARCH" --icon=build/icon.icns \
  --app-bundle-id=org.mnemo.app --app-version=0.1.0 --app-category-type=public.app-category.productivity \
  --extra-resource=../dist/brain --out=../dist --overwrite \
  --ignore='^/build/(icon\.svg|render-icon\.js|icon\.icns)$' --prune=true)
APP="dist/Mnemo-darwin-$ARCH/Mnemo.app"
codesign --force --deep --sign - "$APP"   # ad-hoc signature so macOS will open a locally built app
echo "Built $APP"

if [ "${1:-}" = "--install" ]; then
  rm -rf /Applications/Mnemo.app
  ditto "$APP" /Applications/Mnemo.app
  xattr -cr /Applications/Mnemo.app 2>/dev/null || true          # never quarantined → no "damaged" warning
  codesign --force --deep --sign - /Applications/Mnemo.app
  rm -rf "dist/Mnemo-darwin-$ARCH"   # keep only one Mnemo.app so macOS doesn't list two
  echo "Installed /Applications/Mnemo.app"
fi
