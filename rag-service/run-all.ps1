$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

$ragDir = $PSScriptRoot
$repoRoot = Split-Path -Path $ragDir -Parent
$llamaDir = Join-Path $repoRoot "llama.cpp"

$qwenScript = Join-Path $llamaDir "run-qwen25-7b.ps1"
$bgeScript = Join-Path $llamaDir "run-bge-embed.ps1"
$ragScript = Join-Path $ragDir "run-rag.ps1"

foreach ($script in @($qwenScript, $bgeScript, $ragScript)) {
    if (-not (Test-Path $script)) {
        Write-Error "Missing script: $script"
    }
}

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $qwenScript
)

Start-Sleep -Seconds 2

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $bgeScript
)

Start-Sleep -Seconds 2

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $ragScript
)

Write-Host "Started:"
Write-Host " - Qwen LLM:  http://127.0.0.1:8080"
Write-Host " - BGE Embed: http://127.0.0.1:8081"
Write-Host " - RAG API:   http://127.0.0.1:8090"
Write-Host ""
Write-Host "Health check: http://127.0.0.1:8090/health"
