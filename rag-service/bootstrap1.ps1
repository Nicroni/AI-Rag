param(
    [switch]$DownloadBgeIfMissing,
    [switch]$SkipInstallDeps,
    [switch]$NoStart
)

$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

$ragDir = $PSScriptRoot
$repoRoot = Split-Path -Path $ragDir -Parent
$llamaDir = Join-Path $repoRoot "llama.cpp"

$requirements = Join-Path $ragDir "requirements.txt"
$runAll = Join-Path $ragDir "run-all.ps1"
$qwenScript = Join-Path $llamaDir "run-qwen25-7b.ps1"
$bgeScript = Join-Path $llamaDir "run-bge-embed.ps1"
$downloadBge = Join-Path $llamaDir "download_bge.py"
$llamaServer = Join-Path $llamaDir "build\\bin\\llama-server.exe"
$qwenModel = Join-Path $llamaDir "models\\Qwen2.5-7B-Instruct-Q4_K_M.gguf"

function Assert-Path([string]$path, [string]$label) {
    if (-not (Test-Path $path)) {
        throw "$label not found: $path"
    }
}

function Get-PythonCommand {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) { return "python" }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) { return "py -3" }

    throw "Python not found. Install Python 3.10+ and retry."
}

Write-Host "== Bootstrap: local RAG setup ==" -ForegroundColor Cyan
Write-Host "ragDir:   $ragDir"
Write-Host "llamaDir: $llamaDir"

Assert-Path $ragDir "rag-service folder"
Assert-Path $llamaDir "llama.cpp folder"
Assert-Path $requirements "requirements.txt"
Assert-Path $runAll "run-all.ps1"
Assert-Path $qwenScript "run-qwen25-7b.ps1"
Assert-Path $bgeScript "run-bge-embed.ps1"
Assert-Path $llamaServer "llama-server.exe"

$pythonCmd = Get-PythonCommand
Write-Host "Python command: $pythonCmd"

if (-not $SkipInstallDeps) {
    Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
    Invoke-Expression "$pythonCmd -m pip install -r `"$requirements`""
}

if (-not (Test-Path $qwenModel)) {
    throw "Qwen model missing: $qwenModel"
}

$bgeModelFound = [bool](Get-ChildItem -Path (Join-Path $llamaDir "models") -Filter "*bge*.gguf" -File -ErrorAction SilentlyContinue | Select-Object -First 1)
if (-not $bgeModelFound) {
    if ($DownloadBgeIfMissing) {
        Assert-Path $downloadBge "download_bge.py"
        Write-Host "BGE model missing. Downloading..." -ForegroundColor Yellow
        Push-Location $llamaDir
        try {
            Invoke-Expression "$pythonCmd `"$downloadBge`""
        }
        finally {
            Pop-Location
        }
        $bgeModelFound = [bool](Get-ChildItem -Path (Join-Path $llamaDir "models") -Filter "*bge*.gguf" -File -ErrorAction SilentlyContinue | Select-Object -First 1)
    }
}

if (-not $bgeModelFound) {
    throw "BGE model missing in $llamaDir\\models. Add a *bge*.gguf file or rerun with -DownloadBgeIfMissing."
}

Write-Host "Checks passed." -ForegroundColor Green

if (-not $NoStart) {
    Write-Host "Starting services (Qwen + Embed + RAG)..." -ForegroundColor Yellow
    powershell -NoProfile -ExecutionPolicy Bypass -File $runAll
    Start-Sleep -Seconds 2
    Write-Host "Health endpoint: http://127.0.0.1:8090/health"
}
else {
    Write-Host "NoStart enabled. Services were not launched."
}
