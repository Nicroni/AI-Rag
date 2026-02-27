$ErrorActionPreference = "Stop"

# Run from this script's directory so relative paths are stable.
Set-Location -Path $PSScriptRoot

$server = ".\build\bin\llama-server.exe"
$model = if ($env:EMBED_MODEL_PATH) {
    $env:EMBED_MODEL_PATH
} else {
    $found = Get-ChildItem -Path ".\models" -Filter "*bge*.gguf" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $found.FullName } else { ".\models\bge-m3-q8_0.gguf" }
}

if (-not (Test-Path $server)) {
    Write-Error "llama-server.exe not found: $server"
}

if (-not (Test-Path $model)) {
    Write-Error "Embedding model not found: $model`nSet EMBED_MODEL_PATH to your GGUF file path."
}

& $server `
    -m $model `
    -a text-embedding-3-small `
    --embedding `
    --batch-size 2048 `
    --ubatch-size 1024 `
    --host 127.0.0.1 `
    --port 8081
