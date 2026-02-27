$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

$env:LLM_BASE_URL = "http://127.0.0.1:8080/v1"
$env:EMBED_BASE_URL = "http://127.0.0.1:8081/v1"
$env:LLM_MODEL = "gpt-3.5-turbo"
$env:EMBED_MODEL = "text-embedding-3-small"
$env:CHROMA_DIR = ".\chroma_db"

python -m uvicorn app:app --host 0.0.0.0 --port 8090
