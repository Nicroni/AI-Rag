$ErrorActionPreference = "Stop"

# Run from this script's directory so relative paths are stable.
Set-Location -Path $PSScriptRoot

$server = ".\build\bin\llama-server.exe"
$model = ".\models\Qwen2.5-7B-Instruct-Q4_K_M.gguf"

if (-not (Test-Path $server)) {
    Write-Error "llama-server.exe not found: $server"
}

if (-not (Test-Path $model)) {
    Write-Error "Model not found: $model"
}

& $server `
    -m $model `
    --host 0.0.0.0 `
    --port 8080 `
    --temp 0.15 `
    --top-p 0.8 `
    --top-k 20 `
    --repeat-last-n 256 `
    --repeat-penalty 1.2 `
    --frequency-penalty 0.3 `
    --presence-penalty 0.2 `
    --reasoning-format none `
    --reasoning-budget 0
