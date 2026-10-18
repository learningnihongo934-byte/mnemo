#!/usr/bin/env bash
# Mnemo installer (macOS + Linux; Windows: install.ps1):  curl -fsSL https://raw.githubusercontent.com/learningnihongo934-byte/mnemo/main/install.sh | bash
# Options (after `bash -s --`): --params 125M --context 32768 --no-growth --seq 1024 --mode code --app --dir PATH
set -euo pipefail
REPO="https://github.com/learningnihongo934-byte/mnemo.git"
DIR="$HOME/mnemo"; CFG=(); APP=0
size() { python3 -c "import sys;s=sys.argv[1].upper().rstrip('B') if sys.argv[1].upper().endswith('MB') else sys.argv[1].upper();m={'K':1e3,'M':1e6,'B':1e9,'G':1e9};print(int(float(s[:-1])*m[s[-1]]) if s[-1] in m else int(float(s)))" "$1"; }
while [ $# -gt 0 ]; do
  case "$1" in
    --params)    CFG+=("start_params=$(size "$2")"); shift ;;
    --context)   CFG+=("context_length=$2"); shift ;;
    --seq)       CFG+=("train_seq_len=$2"); shift ;;
    --max)       CFG+=("max_params=$(size "$2")"); shift ;;
    --no-growth) CFG+=("allow_growth=false") ;;
    --mode)      CFG+=("mode=\"$2\""); shift ;;
    --app)       APP=1 ;;
    --dir)       DIR="$2"; shift ;;
    *) echo "Unknown option $1"; exit 1 ;;
  esac; shift
done

# macOS: files downloaded with a web browser carry a "quarantine" flag that makes Gatekeeper call
# unsigned apps "damaged". Clear it from Mnemo's own folder and make sure Electron is signed (ad-hoc).
mac_unquarantine() {
  [ "$(uname)" = Darwin ] || return 0
  xattr -dr com.apple.quarantine "$1" 2>/dev/null || true
  local e="$1/app/node_modules/electron/dist/Electron.app"
  if [ -d "$e" ] && ! codesign -v "$e" 2>/dev/null; then codesign --force --deep --sign - "$e" >/dev/null 2>&1 || true; fi
}
say() { printf "\033[1;35m◉ Mnemo\033[0m %s\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1; }

say "Installing into $DIR"
need git || { say "Git is needed. On a Mac run: xcode-select --install   (then run this again)"; exit 1; }
if ! need node; then
  if need brew; then say "Installing Node with Homebrew…"; brew install node
  else say "Node.js is needed: get it from https://nodejs.org (LTS), then run this again."; exit 1; fi
fi
if ! need uv; then
  PYV=$(python3 -c 'import sys;print(sys.version_info >= (3,10))' 2>/dev/null || echo False)
  if [ "$PYV" != True ]; then say "Installing uv (a small Python manager)…"; curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; fi
fi

if [ -d "$DIR/.git" ]; then say "Updating existing copy…"; git -C "$DIR" pull --ff-only
else git clone --depth 1 "$REPO" "$DIR"; fi
cd "$DIR"
./build.sh

mac_unquarantine "$DIR"
mkdir -p "$HOME/.local/bin"
ln -sf "$DIR/bin/mnemo" "$HOME/.local/bin/mnemo"
for rc in "$HOME/.zshrc" "$HOME/.bashrc"; do
  [ -f "$rc" ] || [ "$rc" = "$HOME/.zshrc" ] || continue
  grep -q '.local/bin' "$rc" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
done
if [ "$(uname)" = Linux ]; then
  sb="$DIR/app/node_modules/electron/dist/chrome-sandbox"
  if [ -f "$sb" ] && command -v sudo >/dev/null; then
    say "Setting up Electron's security sandbox (may ask for your password)…"
    sudo chown root:root "$sb" && sudo chmod 4755 "$sb" || say "Skipped; Mnemo will run without the sandbox."
  fi
fi
[ ${#CFG[@]} -gt 0 ] && "$DIR/bin/mnemo" config "${CFG[@]}"
[ "$APP" = 1 ] && [ "$(uname)" = Darwin ] && "$DIR/bin/mnemo" app

say "Done! Open a new terminal and type:  mnemo"
say "(or run it now with: $DIR/bin/mnemo)"
