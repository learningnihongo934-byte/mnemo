# Mnemo installer for Windows (PowerShell):
#   irm https://raw.githubusercontent.com/learningnihongo934-byte/mnemo/main/install.ps1 | iex
# Installs into %USERPROFILE%\mnemo, adds the `mnemo` command and a Start menu shortcut.
$ErrorActionPreference = "Stop"
$Repo = "https://github.com/learningnihongo934-byte/mnemo.git"
$Dir = if ($env:MNEMO_DIR) { $env:MNEMO_DIR } else { Join-Path $HOME "mnemo" }
function Say($m) { Write-Host "◉ Mnemo " -ForegroundColor Magenta -NoNewline; Write-Host $m }
function Has($c) { [bool](Get-Command $c -ErrorAction SilentlyContinue) }
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") }

Say "Installing into $Dir"
foreach ($pkg in @(@{cmd="git"; id="Git.Git"}, @{cmd="node"; id="OpenJS.NodeJS.LTS"})) {
  if (-not (Has $pkg.cmd)) {
    if (Has "winget") { Say "Installing $($pkg.cmd)…"; winget install -e --id $pkg.id --accept-source-agreements --accept-package-agreements | Out-Null; Refresh-Path }
    else { Say "Please install $($pkg.cmd) first (https://git-scm.com, https://nodejs.org), then run this again."; exit 1 }
  }
}
if (-not (Has "uv")) { Say "Installing uv (a small Python manager)…"; Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression; Refresh-Path; $env:Path += ";$HOME\.local\bin" }

if (Test-Path "$Dir\.git") { Say "Updating existing copy…"; git -C $Dir pull --ff-only } else { git clone --depth 1 $Repo $Dir }
Set-Location $Dir

Say "Setting up Python (3.12)…"
if (-not (Test-Path ".venv")) { uv venv --python 3.12 .venv }
$py = Join-Path $Dir ".venv\Scripts\python.exe"
if (Has "nvidia-smi") {
  Say "NVIDIA GPU found: installing PyTorch with CUDA."
  uv pip install --python $py torch --index-url https://download.pytorch.org/whl/cu124
}
uv pip install --python $py -r requirements.txt

Say "Setting up the desktop app…"
Push-Location app; npm install --no-fund --no-audit; Pop-Location

# `mnemo` command
$bin = Join-Path $HOME ".local\bin"; New-Item -ItemType Directory -Force $bin | Out-Null
Set-Content -Path (Join-Path $bin "mnemo.cmd") -Value "@echo off`r`ncall `"$Dir\bin\mnemo.cmd`" %*" -Encoding ASCII
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$bin*") { [Environment]::SetEnvironmentVariable("Path", "$userPath;$bin", "User") }

# Start menu shortcut
$lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "Mnemo.lnk"
$sh = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$sh.TargetPath = Join-Path $Dir "app\node_modules\electron\dist\electron.exe"
$sh.Arguments = "`"$Dir\app`""; $sh.WorkingDirectory = "$Dir\app"
$sh.IconLocation = Join-Path $Dir "app\build\icon.ico"; $sh.Save()

Say "Done! Open Mnemo from the Start menu, or type  mnemo  in a new terminal."
