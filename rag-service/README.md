# Local RAG Service (FastAPI + llama.cpp)

This service adds retrieval-augmented generation (RAG) on top of your existing local `llama-server` setup:

- LLM endpoint: `http://127.0.0.1:8080/v1`
- Embedding endpoint: `http://127.0.0.1:8081/v1`
- RAG API endpoint: `http://127.0.0.1:8090`

## 1) Start llama.cpp servers

Run your chat model (`qwen`) and embedding model first.

Model names used by this service:
- LLM model name (request field): `gpt-3.5-turbo`
- embedding model alias: `text-embedding-3-small`

## 2) Install Python dependencies

```powershell
cd D:\LLM\rag-service
pip install -r requirements.txt
```

## Bootstrap (new machine)

After clone, run one script to validate setup, install deps, and start services.

```powershell
cd <repo>\rag-service
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap1.ps1
```

Useful options:
- `-SkipInstallDeps` (skip `pip install`)
- `-NoStart` (only check environment, do not launch services)
- `-DownloadBgeIfMissing` (try to download BGE model via `download_bge.py`)

## 3) Start RAG API

```powershell
cd D:\LLM\rag-service
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-rag.ps1
```

## One-command startup (Qwen + BGE + RAG)

This starts all 3 services in separate PowerShell windows.

```powershell
cd D:\LLM\rag-service
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-all.ps1
```

Note: make sure embedding model exists at `D:\LLM\llama.cpp\models\bge-m3-q8_0.gguf`.

## 4) Build index from documents

Create a folder like `D:\LLM\rag-service\docs` and put `.txt`, `.md`, `.pdf`, `.docx` files there.

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8090/index" -ContentType "application/json" -Body '{"path":"D:\\LLM\\rag-service\\docs","collection":"kb_docs","recursive":true,"rebuild":true}'
```

## 5) Ask questions

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8090/query" -ContentType "application/json" -Body '{"question":"Энэ баримтуудаас гол шаардлагуудыг товч хэл","collection":"kb_docs","top_k":4}'
```

## Endpoints

- `GET /health`
- `POST /index`
- `POST /query`

`POST /query` response includes:
- `answer` (raw model output)
- `answer_text` (parsed main answer)
- `confidence` (parsed, if present)
- `status` (parsed, if present)
- `sources` with:
  - `file`
  - `score`
  - `preview` (chunk preview)
  - `line_start` / `line_end` (best effort)

## Notes

- This RAG layer enforces stricter fact-check style in Mongolian via QA prompt template.
- If you switch llama.cpp ports/models, edit `run-rag.ps1` environment variables.

## Phase 1 Baseline Eval

Run baseline evaluation with 30 questions and freeze the current quality metrics.

```powershell
cd D:\LLM\rag-service
python .\eval\run_eval.py --base-url http://127.0.0.1:8090 --dataset .\eval\questions.phase1.json --top-k 4
```

Report is saved to:
- `eval\reports\baseline_YYYYMMDD_HHMMSS.json`

Key summary metrics:
- `answer_match_rate`
- `citation_coverage`
- `refusal_rate_on_expected_refusal`
- `avg_latency_ms`
