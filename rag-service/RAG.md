# RAG Project Guide (llama.cpp + FastAPI)

Энэ файл нь төслийг эхнээс нь дуустал тайлбарласан бүрэн гарын авлага.

## 1. Төслийн зорилго

Энэ төсөл нь local орчинд ажиллах RAG (Retrieval-Augmented Generation) систем юм.

- LLM: `llama.cpp` дээр ажиллаж буй chat model (Qwen 2.5 7B)
- Embedding: `llama.cpp` дээр ажиллаж буй embedding model (BGE)
- RAG API: FastAPI service (`rag-service/app.py`)
- Vector DB: Chroma (`rag-service/chroma_db`)

Үндсэн зорилго:
- Баримтаас хариулах
- Source citation буцаах (`file`, `preview`, `line_start`, `line_end`)
- Structured output буцаах (`answer_text`, `confidence`, `status`)

---

## 2. Архитектур

Компонентууд:

1. `llama-server` (chat)  
   - URL: `http://127.0.0.1:8080/v1`
   - Model нэр (OpenAI compatible request талд): `gpt-3.5-turbo`

2. `llama-server` (embedding)  
   - URL: `http://127.0.0.1:8081/v1`
   - Embedding model alias: `text-embedding-3-small`

3. `rag-service` (FastAPI)  
   - URL: `http://127.0.0.1:8090`
   - Endpoints:
     - `GET /health`
     - `POST /index`
     - `POST /query`

Data flow:
- `/index` -> docs уншина -> chunk/embedding -> Chroma-д хадгална
- `/query` -> retrieve хийнэ -> LLM-ээр answer synthesize -> structured + citations буцаана

---

## 3. Хавтас бүтэц

`rag-service` дотор:

- `app.py` – RAG API үндсэн код
- `requirements.txt` – Python dependencies
- `run-rag.ps1` – зөвхөн RAG API асаана
- `run-all.ps1` – chat + embed + rag-г зэрэг асаана
- `bootstrap1.ps1` – шинэ машинд setup автоматжуулах script
- `docs/` – индексжүүлэх баримтууд
- `chroma_db/` – local vector DB
- `eval/` – evaluation scripts/datasets
  - `eval/run_eval.py`
  - `eval/questions.phase1.json`

`llama.cpp` дотор:

- `run-qwen25-7b.ps1` – chat model асаана
- `run-bge-embed.ps1` – embedding model асаана
- `download_bge.py` – BGE model татах helper

---

## 4. Шаардлага

Шинэ компьютер дээр шаардлагатай зүйлс:

1. Windows + PowerShell
2. Python 3.10+ (`python --version`)
3. `llama.cpp` build хийгдсэн (`build/bin/llama-server.exe` байгаа)
4. Models:
   - Chat model: `Qwen2.5-7B-Instruct-Q4_K_M.gguf`
   - Embedding model: `*bge*.gguf`

Анхаарах:
- `.gguf` model файлууд repo-д орохгүй (`.gitignore`), тиймээс тусад нь бэлдэх хэрэгтэй.

---

## 5. Git clone ба анхны setup

## 5.1 Clone

```powershell
git clone <YOUR_REPO_URL>
cd <repo>\rag-service
```

## 5.2 Нэг командаар bootstrap

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap1.ps1
```

Энэ script:
- Python command шалгана
- `requirements.txt` суулгана
- `llama.cpp`/scripts/models байгаа эсэхийг шалгана
- хүсвэл model татна
- `run-all.ps1` дуудаж services-ийг асаана

Сонголтууд:

```powershell
# dependency install алгасах
powershell -File .\bootstrap1.ps1 -SkipInstallDeps

# зөвхөн check хийх, service асаахгүй
powershell -File .\bootstrap1.ps1 -NoStart

# BGE model байхгүй бол татах оролдлого хийх
powershell -File .\bootstrap1.ps1 -DownloadBgeIfMissing
```

---

## 6. Гар аргаар setup (manual)

Хэрэв bootstrap ашиглахгүй бол:

1. Python deps:
```powershell
cd <repo>\rag-service
pip install -r requirements.txt
```

2. Chat model асаах:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <repo>\llama.cpp\run-qwen25-7b.ps1
```

3. Embedding model асаах:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <repo>\llama.cpp\run-bge-embed.ps1
```

4. RAG API асаах:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <repo>\rag-service\run-rag.ps1
```

5. Health check:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8090/health"
```

Хүлээгдэх хариу:
```json
{"status":"ok"}
```

---

## 7. Model бэлдэх

## 7.1 Chat model

`llama.cpp\models\Qwen2.5-7B-Instruct-Q4_K_M.gguf` замд байрлуул.

## 7.2 Embedding model

`llama.cpp\models\*bge*.gguf` pattern-т таарах embedding model байрлуул.

Хэрэв байхгүй бол:
```powershell
cd <repo>\llama.cpp
python -m pip install huggingface_hub
python .\download_bge.py
```

---

## 8. Docs индексжүүлэх

1. Баримтуудаа `docs/` дотор хийнэ (`.txt`, `.md`, `.pdf`, `.docx`)

2. Index request:
```powershell
$body = @{
  path = "<repo>\rag-service\docs"
  collection = "kb_docs"
  recursive = $true
  rebuild = $true
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8090/index" -ContentType "application/json; charset=utf-8" -Body $body
```

Амжилттай бол:
```text
status indexed_docs collection
ok     N          kb_docs
```

---

## 9. Query хийх

```powershell
$q = @{
  question = "What is the main goal?"
  collection = "kb_docs"
  top_k = 4
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8090/query" -ContentType "application/json; charset=utf-8" -Body $q | ConvertTo-Json -Depth 6
```

Response fields:
- `answer`: raw model output
- `answer_text`: parsed core answer
- `confidence`
- `status`
- `sources[]`:
  - `file`
  - `score`
  - `preview`
  - `line_start`
  - `line_end`

---

## 10. Encoding асуудал (PowerShell 5)

Windows PowerShell 5 дээр Unicode харагдахгүй бол:

```powershell
chcp 65001
[Console]::InputEncoding  = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
```

Илүү найдвартай:
- PowerShell 7 (`pwsh`) ашиглах

---

## 11. Evaluation (Phase 1 baseline)

Dataset:
- `eval/questions.phase1.json` (30 асуулт)

Run:
```powershell
cd <repo>\rag-service
python .\eval\run_eval.py --base-url http://127.0.0.1:8090 --dataset .\eval\questions.phase1.json --top-k 4 --out .\eval\reports\baseline_phase1_live.json
```

Metrics:
- `answer_match_rate`
- `citation_coverage`
- `refusal_rate_on_expected_refusal`
- `avg_latency_ms`

Тэмдэглэл:
- `run_eval.py` нь одоо progress-оо алхам бүрд файл руу хадгалдаг.

---

## 12. Troubleshooting

## 12.1 `127.0.0.1:8090 refused`
- `run-rag.ps1` ажиллаж байгаа эсэхийг шалга
- `pip install -r requirements.txt` дахин хий

## 12.2 `/index` дээр 500
- `collection="kb_docs"` ашиглаж байгаа эсэх
- `docs/` хоосон биш эсэх

## 12.3 `/query` дээр утгагүй/encoding эвдэрхий
- UTF-8 settings хий (`chcp 65001`)
- English question өгвөл English output prompt ашиглагдана

## 12.4 Embedding server асахгүй
- `*bge*.gguf` файл байгаа эсэх
- `EMBED_MODEL_PATH` env var-р explicit зааж болно

## 12.5 `HTTPS is not supported` (llama.cpp download flags)
- Built-in remote download биш, Python (`download_bge.py`) ашиглаж model татаарай

---

## 13. GitHub-д юу commit хийх вэ

Commit хийх:
- code/scripts/docs/eval dataset

Commit хийхгүй:
- `chroma_db/`
- `eval/reports/`
- `last_response.json`
- model files (`*.gguf`)

`.gitignore` аль хэдийн тохирсон.

---

## 14. Production-д оруулахын өмнөх checklist

1. `health` OK
2. `index` OK
3. `query` дээр citation гарч байна
4. `eval` report хадгалагдсан
5. latency болон refusal behavior шаардлага хангаж байна

---

## 15. Хурдан командууд (copy-paste)

```powershell
# Start all services
cd <repo>\rag-service
powershell -NoProfile -ExecutionPolicy Bypass -File .\run-all.ps1
```

```powershell
# Health
Invoke-RestMethod http://127.0.0.1:8090/health
```

```powershell
# Index
$body = @{ path="<repo>\rag-service\docs"; collection="kb_docs"; recursive=$true; rebuild=$true } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8090/index" -ContentType "application/json; charset=utf-8" -Body $body
```

```powershell
# Query
$q = @{ question="What is the main goal?"; collection="kb_docs"; top_k=4 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8090/query" -ContentType "application/json; charset=utf-8" -Body $q | ConvertTo-Json -Depth 6
```
