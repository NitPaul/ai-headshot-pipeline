<#
    WeGro Employee Photo Tool - one time setup.

    Started by setup.bat. Installs Python if the computer does not have a
    suitable version, then builds a private environment for the tool and
    downloads the models it needs.

    Nothing here needs administrator rights: Python is installed for the
    current user only.
#>

$ErrorActionPreference = 'Stop'

# rembg needs 3.11 or newer, and nothing supports 4.x yet.
$MinMinor      = 11
$InstallMinor  = 12
$InstallVersion = '3.12.10'

$Root = Split-Path -Parent $PSScriptRoot


function Say([string]$Text, [string]$Colour = 'Gray') {
    Write-Host $Text -ForegroundColor $Colour
}

function Step([int]$Number, [string]$Text) {
    Write-Host ""
    Write-Host "  [$Number/5] $Text" -ForegroundColor Cyan
}


function Test-Python {
    <# Returns the version as a string if this command is a usable Python.

       The probe below deliberately contains no quotation marks. PowerShell
       strips quotes when handing arguments to a native program, which turns
       any quoted Python one-liner into a syntax error.
    #>
    param([string]$Exe, [string[]]$Arguments = @())
    try {
        $probe = 'import sys;print(sys.version_info.major*100+sys.version_info.minor)'
        $output = & $Exe @Arguments '-c' $probe 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $output) { return $null }

        $code = 0
        if (-not [int]::TryParse("$output".Trim(), [ref]$code)) { return $null }

        $major = [math]::Floor($code / 100)
        $minor = $code % 100
        if ($major -eq 3 -and $minor -ge $MinMinor) { return "$major.$minor" }
    } catch { }
    return $null
}


function Find-Python {
    <# Look everywhere Python might already be, newest sensible one first. #>
    $candidates = @()

    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in '3.12', '3.13', '3.11') {
            $candidates += , @{ Exe = 'py'; Args = @("-$v") }
        }
        $candidates += , @{ Exe = 'py'; Args = @('-3') }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        $candidates += , @{ Exe = 'python'; Args = @() }
    }

    # Installed but not on PATH - common when PATH has not refreshed yet.
    $searchRoots = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python'),
        'C:\Program Files',
        'C:\'
    )
    foreach ($root in $searchRoots) {
        if (-not (Test-Path $root)) { continue }
        Get-ChildItem $root -Directory -Filter 'Python3*' -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object {
                $exe = Join-Path $_.FullName 'python.exe'
                if (Test-Path $exe) { $candidates += , @{ Exe = $exe; Args = @() } }
            }
    }

    foreach ($c in $candidates) {
        $version = Test-Python -Exe $c.Exe -Arguments $c.Args
        if ($version) {
            return @{ Exe = $c.Exe; Args = $c.Args; Version = $version }
        }
    }
    return $null
}


function Install-Python {
    <# Per-user silent install from python.org. No administrator rights needed. #>
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
    $file = "python-$InstallVersion-$arch.exe"
    $url  = "https://www.python.org/ftp/python/$InstallVersion/$file"
    $temp = Join-Path $env:TEMP $file

    Say "        Python $InstallVersion is being downloaded (about 25 MB)."
    Say "        This is the official installer from python.org."

    $progressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri $url -OutFile $temp -UseBasicParsing

    Say "        Installing. This takes a couple of minutes, please wait..."
    $arguments = @(
        '/quiet',
        'InstallAllUsers=0',      # current user only, so no admin prompt
        'PrependPath=1',          # puts python on PATH for future windows
        'Include_pip=1',
        'Include_launcher=1',
        'Include_test=0'
    )
    $process = Start-Process -FilePath $temp -ArgumentList $arguments -Wait -PassThru
    Remove-Item $temp -ErrorAction SilentlyContinue

    if ($process.ExitCode -ne 0 -and $process.ExitCode -ne 3010) {
        throw "The Python installer failed with code $($process.ExitCode)."
    }
}


# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor White
Write-Host "    WeGro Employee Photo Tool  -  ONE TIME SETUP" -ForegroundColor White
Write-Host "  ============================================================" -ForegroundColor White
Write-Host ""
Say "  This needs an internet connection and takes about 10 minutes."
Say "  You only ever have to do this once on this computer."

Set-Location $Root

# --- 1. Python -------------------------------------------------------------
Step 1 "Checking for Python"

$python = Find-Python
if ($python) {
    Say "        Found Python $($python.Version). Nothing to install." Green
} else {
    Say "        Python is not installed. Installing it now for you." Yellow
    Install-Python
    $python = Find-Python
    if (-not $python) {
        throw "Python was installed but could not be found afterwards. " +
              "Please restart the computer and run setup.bat again."
    }
    Say "        Python $($python.Version) installed." Green
}

# --- 2. Private environment ------------------------------------------------
Step 2 "Creating a private environment for the tool"

$venvPython = Join-Path $Root '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
    Say "        Already exists."
} else {
    & $python.Exe @($python.Args) -m venv (Join-Path $Root '.venv')
    if (-not (Test-Path $venvPython)) { throw "The environment could not be created." }
    Say "        Done." Green
}

# --- 3. Components ---------------------------------------------------------
Step 3 "Installing the components (this is the slow part)"

& $venvPython -m pip install --upgrade pip --quiet --disable-pip-version-check
& $venvPython -m pip install -r (Join-Path $Root 'requirements.txt') --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) {
    throw "The components could not be installed. Check the internet connection and try again."
}
Say "        Done." Green

# --- 4. Models -------------------------------------------------------------
Step 4 "Downloading the face models (about 220 MB)"

$env:PYTHONPATH = Join-Path $Root 'src'
& $venvPython -m wegro_headshot.setup_models
if ($LASTEXITCODE -ne 0) {
    Say "        [!] Something could not be downloaded. See the message above." Yellow
}

# --- 5. API key ------------------------------------------------------------
Step 5 "Checking the Google API key"

$envFile = Join-Path $Root '.env'
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $Root '.env.example') $envFile
}

$needsKey = (Get-Content $envFile -Raw) -match 'paste_your_key_here'

Write-Host ""
if ($needsKey) {
    Write-Host "  ------------------------------------------------------------" -ForegroundColor Yellow
    Write-Host "   ALMOST DONE - one thing left to do" -ForegroundColor Yellow
    Write-Host "  ------------------------------------------------------------" -ForegroundColor Yellow
    Say "   1. Go to  https://aistudio.google.com/apikey"
    Say "   2. Sign in and click 'Create API key'. It is free."
    Say "   3. Copy the key."
    Say "   4. A file called  .env  is in this folder."
    Say "      Open it with Notepad and paste the key after the = sign."
    Write-Host ""
    Say "   Then put employee photos in 01_inbox and run  run.bat"

    $answer = Read-Host "`n   Open the .env file in Notepad now? (y/n)"
    if ($answer -match '^[Yy]') { Start-Process notepad.exe $envFile }
} else {
    Write-Host "  ------------------------------------------------------------" -ForegroundColor Green
    Write-Host "   SETUP COMPLETE" -ForegroundColor Green
    Write-Host "  ------------------------------------------------------------" -ForegroundColor Green
    Say "   Put employee photos in the 01_inbox folder,"
    Say "   then double-click  run.bat"
}
Write-Host ""
