# CopyClip installer/updater for Windows
# Install: irm https://raw.githubusercontent.com/sssamuelll/copyclip/main/install.ps1 | iex
# Update:  irm https://raw.githubusercontent.com/sssamuelll/copyclip/main/install.ps1 | iex

$ErrorActionPreference = "Stop"
$REPO = "https://github.com/sssamuelll/copyclip.git"
$MIN_PYTHON = "3.10"

function Write-Info($msg)  { Write-Host "[copyclip] " -ForegroundColor Cyan -NoNewline; Write-Host $msg }
function Write-Ok($msg)    { Write-Host "[copyclip] " -ForegroundColor Green -NoNewline; Write-Host $msg }
function Write-Err($msg)   { Write-Host "[copyclip] " -ForegroundColor Red -NoNewline; Write-Host $msg }

# --- Check Python version ---
$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        $major = [int]($ver.Split('.')[0])
        $minor = [int]($ver.Split('.')[1])
        if ($major -ge 3 -and $minor -ge 10) {
            $python = $cmd
            break
        }
    } catch { }
}

if (-not $python) {
    Write-Err "Python ${MIN_PYTHON}+ is required but not found."
    Write-Err "Install Python from https://python.org/downloads/ and try again."
    Write-Err "Make sure to check 'Add Python to PATH' during installation."
    exit 1
}

$pyver = & $python --version 2>&1
Write-Info "Found $python ($pyver)"

# --- Detect existing installation ---
$upgrading = $false
try {
    $null = Get-Command copyclip -ErrorAction Stop
    $upgrading = $true
    Write-Info "Existing copyclip found - upgrading..."
} catch { }

# --- Install/upgrade via pipx (preferred) or pip ---
$usePipx = $false
try {
    $null = Get-Command pipx -ErrorAction Stop
    $usePipx = $true
} catch { }

if ($usePipx) {
    if ($upgrading) {
        Write-Info "Upgrading with pipx..."
        try { pipx upgrade copyclip } catch { pipx install "copyclip @ git+${REPO}" --force }
    } else {
        Write-Info "Installing with pipx (isolated environment)..."
        pipx install "copyclip @ git+${REPO}" --force
    }
} else {
    $action = if ($upgrading) { "Upgrading" } else { "Installing" }
    Write-Info "$action with pip --user..."
    & $python -m pip install --user --upgrade "copyclip @ git+${REPO}"
}

# --- Verify installation ---
try {
    $null = Get-Command copyclip -ErrorAction Stop
    if ($upgrading) { Write-Ok "copyclip upgraded successfully!" } else { Write-Ok "copyclip installed successfully!" }
    Write-Host ""
    Write-Ok "Get started:"
    Write-Host "  cd your-project"
    Write-Host "  copyclip start"
} catch {
    Write-Host ""
    Write-Err "copyclip was installed but is not in your PATH."
    Write-Host ""

    $scriptDir = & $python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))" 2>$null
    if (-not $scriptDir) {
        $scriptDir = "$env:APPDATA\Python\Scripts"
    }

    Write-Info "Add this directory to your PATH:"
    Write-Host ""
    Write-Host "  $scriptDir"
    Write-Host ""
    Write-Info "To add permanently, run this in PowerShell as Administrator:"
    Write-Host ""
    Write-Host "  [Environment]::SetEnvironmentVariable('PATH', `$env:PATH + ';${scriptDir}', 'User')"
    Write-Host ""
    Write-Info "Then restart your terminal."
}
