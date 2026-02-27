import os
import re
import json
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional

import chromadb
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional fallback if dotenv is missing
    def load_dotenv(*_args, **_kwargs):
        return False

from llama_index.core import Settings, SimpleDirectoryReader, StorageContext, VectorStoreIndex
from llama_index.core.prompts import PromptTemplate
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.chroma import ChromaVectorStore


BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")


DEFAULT_DOMAIN_NAME = os.getenv("DOMAIN_NAME", "Windows OS logs and production incident analysis")

DEFAULT_SYSTEM_PROMPT_MN = os.getenv(
    "SYSTEM_PROMPT_MN",
    (
        "Та бол Windows OS лог, үйлдлийн алдаа, production инцидент шинжилгээнд мэргэшсэн ахлах инженер. "
        "Баримтгүй таамаг дэвшүүлэхгүй. Оношлохдоо evidence -> inference -> action дарааллаар бод. "
        "Хэрэв контекст дутуу бол тодорхой 'мэдээлэл хүрэлцэхгүй' гэж хэлж, дараагийн шалгах алхмуудыг товч өг."
    ),
)

DEFAULT_SYSTEM_PROMPT_EN = os.getenv(
    "SYSTEM_PROMPT_EN",
    (
        "You are a senior engineer specialized in Windows OS logs, production incident analysis, and root-cause debugging. "
        "Do not invent facts. Reason in evidence -> inference -> action order. "
        "If context is insufficient, explicitly state insufficient data and provide concise next checks."
    ),
)

STRICT_CONTEXT_MODE = os.getenv("STRICT_CONTEXT_MODE", "true").strip().lower() in {"1", "true", "yes", "on"}
MIN_SOURCE_SCORE = float(os.getenv("MIN_SOURCE_SCORE", "0.20"))
TOP_K_DEFAULT = int(os.getenv("TOP_K_DEFAULT", "4"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "320"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "64"))
WINDOWS_LOG_QUERY_TIMEOUT_SEC = int(os.getenv("WINDOWS_LOG_QUERY_TIMEOUT_SEC", "30"))
WINDOWS_LOG_MAX_EVENTS = int(os.getenv("WINDOWS_LOG_MAX_EVENTS", "200"))
WINDOWS_LOG_DEFAULT_HOURS_BACK = int(os.getenv("WINDOWS_LOG_DEFAULT_HOURS_BACK", "2"))

WINDOWS_ALLOWED_CHANNELS = [
    "System",
    "Application",
    "Security",
    "Setup",
    "Microsoft-Windows-TaskScheduler/Operational",
    "Microsoft-Windows-WindowsUpdateClient/Operational",
    "Microsoft-Windows-DNS-Client/Operational",
    "Microsoft-Windows-GroupPolicy/Operational",
]


def _build_mn_template(system_prompt_mn: str) -> PromptTemplate:
    return PromptTemplate(
        "Контекст:\n"
        "---------------------\n"
        "{context_str}\n"
        "---------------------\n"
        f"Домэйн: {DEFAULT_DOMAIN_NAME}\n"
        f"Системийн заавар: {system_prompt_mn}\n\n"
        "Хариултын хатуу дүрэм:\n"
        "1) Зөвхөн Монгол кириллээр хариул.\n"
        "2) Баримтгүй бол зохиохгүй, 'мэдээлэл хүрэлцэхгүй' гэж хэл.\n"
        "3) Алдааны боломжит шалтгааныг evidence дээр тулгаж жагсаа.\n"
        "4) Эхлээд root cause магадлалууд, дараа нь хамгийн ойрын засварын алхмыг өг.\n"
        "5) Давталтгүй, товч, хэрэгжихүйц бай.\n\n"
        "Асуулт: {query_str}\n\n"
        "Хариултын формат:\n"
        "- Хариулт: <1-4 өгүүлбэр>\n"
        "- Итгэлцүүр: <Өндөр|Дунд|Бага>\n"
        "- Төлөв: <Баттай|Баталгаажуулалт шаардлагатай|Мэдээлэл хүрэлцэхгүй>\n"
    )


def _build_en_template(system_prompt_en: str) -> PromptTemplate:
    return PromptTemplate(
        "Context:\n"
        "---------------------\n"
        "{context_str}\n"
        "---------------------\n"
        f"Domain: {DEFAULT_DOMAIN_NAME}\n"
        f"System instruction: {system_prompt_en}\n\n"
        "Hard rules:\n"
        "1) Do not invent facts when context is missing.\n"
        "2) Provide likely root causes only if grounded in evidence.\n"
        "3) Keep response concise and actionable.\n\n"
        "Question: {query_str}\n\n"
        "Response format:\n"
        "- Answer: <1-4 sentences>\n"
        "- Confidence: <High|Medium|Low>\n"
        "- Status: <Confirmed|Needs verification|Insufficient data>\n"
    )


def _has_cyrillic(text: str) -> bool:
    return bool(re.search(r"[\u0400-\u04FF]", text or ""))


def _extract_field(text: str, labels: list[str]) -> Optional[str]:
    for label in labels:
        # Support both "- Label: value" and "Label: value"
        m = re.search(rf"(?:^|\n)\s*-?\s*{re.escape(label)}\s*:\s*(.+)", text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _parse_structured_answer(text: str) -> dict:
    answer_text = _extract_field(text, ["Хариулт", "Answer"])
    confidence = _extract_field(text, ["Итгэлцүүр", "Confidence"])
    status = _extract_field(text, ["Төлөв", "Status"])

    # Fallback: if no structured format detected, keep full output in answer_text.
    if not answer_text:
        answer_text = text.strip()

    return {
        "answer_text": answer_text,
        "confidence": confidence,
        "status": status,
    }


def _parse_rca_sections(text: str) -> dict:
    lines = (text or "").splitlines()
    sections = {
        "root_cause": [],
        "evidence": [],
        "actions": [],
        "risk": [],
    }
    current = None

    for raw in lines:
        line = raw.strip()
        low = line.lower()
        if not line:
            continue
        if ("root cause" in low) or ("үндсэн шалтгаан" in low):
            current = "root_cause"
            continue
        if ("evidence" in low) or ("нотолгоо" in low):
            current = "evidence"
            continue
        if ("action" in low) or ("алхам" in low) or ("mitigation" in low):
            current = "actions"
            continue
        if ("risk" in low) or ("эрсдэл" in low):
            current = "risk"
            continue
        if current:
            cleaned = line.lstrip("-*0123456789. ").strip()
            if cleaned:
                sections[current].append(cleaned)

    # fallback: if parsing failed, keep whole answer under root_cause
    if not any(sections.values()):
        whole = (text or "").strip()
        if whole:
            sections["root_cause"] = [whole]
    return sections


def _read_text_best_effort(file_path: str) -> str:
    if not file_path:
        return ""
    try:
        return Path(file_path).read_text(encoding="utf-8")
    except Exception:
        try:
            return Path(file_path).read_text(encoding="utf-8-sig")
        except Exception:
            try:
                return Path(file_path).read_text(encoding="cp1252")
            except Exception:
                return ""


def _char_idx_to_line(text: str, idx: int) -> int:
    if idx <= 0:
        return 1
    idx = min(idx, len(text))
    return text.count("\n", 0, idx) + 1


def _extract_preview(node, max_len: int = 220) -> str:
    raw = ""
    if hasattr(node, "text") and isinstance(node.text, str):
        raw = node.text
    if not raw:
        try:
            raw = node.get_content()
        except Exception:
            raw = ""
    raw = (raw or "").strip().replace("\r", " ").replace("\n", " ")
    if len(raw) <= max_len:
        return raw
    return raw[: max_len - 1] + "…"


def _infer_line_range(file_path: str, metadata: dict, preview: str) -> tuple[Optional[int], Optional[int]]:
    # Preferred path: use char indices from metadata when available.
    s = metadata.get("start_char_idx")
    e = metadata.get("end_char_idx")
    if isinstance(s, int) and isinstance(e, int) and file_path:
        text = _read_text_best_effort(file_path)
        if text:
            return _char_idx_to_line(text, s), _char_idx_to_line(text, e)

    # Fallback: best-effort preview lookup.
    if file_path and preview:
        text = _read_text_best_effort(file_path)
        if text:
            probe = preview.replace("…", "").strip()
            pos = text.find(probe)
            if pos >= 0:
                line = _char_idx_to_line(text, pos)
                return line, line
    return None, None


class IndexRequest(BaseModel):
    path: str = Field(..., description="Folder path for source files")
    collection: str = Field(default="kb_docs", description="Chroma collection name (3+ chars)")
    recursive: bool = Field(default=True)
    rebuild: bool = Field(default=False, description="Drop and recreate collection")


class QueryRequest(BaseModel):
    question: str
    collection: str = Field(default="kb_docs")
    top_k: int = Field(default=TOP_K_DEFAULT, ge=1, le=20)


MN_QA_TEMPLATE = _build_mn_template(DEFAULT_SYSTEM_PROMPT_MN)
EN_QA_TEMPLATE = _build_en_template(DEFAULT_SYSTEM_PROMPT_EN)


class WindowsLogQueryRequest(BaseModel):
    channel: str = Field(default="System")
    hours_back: int = Field(default=WINDOWS_LOG_DEFAULT_HOURS_BACK, ge=1, le=168)
    event_ids: list[int] = Field(default_factory=list)
    levels: list[int] = Field(default_factory=list, description="1=Critical,2=Error,3=Warning,4=Info,5=Verbose")
    max_events: int = Field(default=100, ge=1, le=WINDOWS_LOG_MAX_EVENTS)


class WindowsLogAnalyzeRequest(BaseModel):
    question: str
    channel: str = Field(default="System")
    hours_back: int = Field(default=WINDOWS_LOG_DEFAULT_HOURS_BACK, ge=1, le=168)
    event_ids: list[int] = Field(default_factory=list)
    levels: list[int] = Field(default_factory=list)
    max_events: int = Field(default=50, ge=1, le=100)


def _powershell_quote(s: str) -> str:
    return s.replace("'", "''")


def _run_windows_log_query(req: WindowsLogQueryRequest) -> list[dict]:
    channel = req.channel.strip()
    if channel not in WINDOWS_ALLOWED_CHANNELS:
        raise HTTPException(status_code=400, detail=f"Unsupported channel: {channel}")

    ids = [int(x) for x in req.event_ids if isinstance(x, int) or str(x).isdigit()]
    levels = [int(x) for x in req.levels if str(x).isdigit() and 1 <= int(x) <= 5]
    ids_ps = ",".join(str(x) for x in ids)
    levels_ps = ",".join(str(x) for x in levels)

    script = f"""
$ErrorActionPreference = 'Stop'
$start = (Get-Date).AddHours(-{req.hours_back})
$fh = @{{ LogName = '{_powershell_quote(channel)}'; StartTime = $start }}
if ('{ids_ps}' -ne '') {{ $fh.Id = @({ids_ps}) }}
if ('{levels_ps}' -ne '') {{ $fh.Level = @({levels_ps}) }}
$events = Get-WinEvent -FilterHashtable $fh -MaxEvents {req.max_events} |
  Select-Object TimeCreated, Id, LevelDisplayName, ProviderName, MachineName, LogName, RecordId, Message
$events | ConvertTo-Json -Depth 5 -Compress
"""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=WINDOWS_LOG_QUERY_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Windows log query timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run PowerShell query: {e}")

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "Unknown PowerShell error").strip()
        raise HTTPException(status_code=500, detail=f"Windows log query failed: {detail}")

    out = (proc.stdout or "").strip()
    if not out:
        return []
    try:
        parsed = json.loads(out)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse Windows log output: {e}")

    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return parsed
    return []


def _llm_chat(messages: list[dict]) -> str:
    llm_base = os.getenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")
    model = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    url = f"{llm_base}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
    }
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=WINDOWS_LOG_QUERY_TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse LLM response: {e}")


class RAGService:
    def __init__(self) -> None:
        llm_base = os.getenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1")
        embed_base = os.getenv("EMBED_BASE_URL", "http://127.0.0.1:8081/v1")
        llm_model = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
        embed_model = os.getenv("EMBED_MODEL", "text-embedding-3-small")
        persist_dir = os.getenv("CHROMA_DIR", "./chroma_db")

        Settings.llm = OpenAI(
            model=llm_model,
            api_base=llm_base,
            api_key="none",
            temperature=0,
        )
        Settings.embed_model = OpenAIEmbedding(
            model=embed_model,
            api_base=embed_base,
            api_key="none",
        )
        # Keep chunks small enough for embedding server physical batch limits.
        Settings.chunk_size = CHUNK_SIZE
        Settings.chunk_overlap = CHUNK_OVERLAP

        self.chroma = chromadb.PersistentClient(path=persist_dir)

    def _collection(self, name: str, rebuild: bool = False):
        try:
            if rebuild:
                try:
                    self.chroma.delete_collection(name)
                except Exception:
                    pass
            return self.chroma.get_or_create_collection(name=name)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid collection name '{name}': {e}")

    def build_index(self, req: IndexRequest) -> dict:
        source_path = Path(req.path)
        if not source_path.exists():
            raise HTTPException(status_code=400, detail=f"Path not found: {req.path}")
        if not source_path.is_dir():
            raise HTTPException(status_code=400, detail=f"Path is not a directory: {req.path}")

        try:
            docs = SimpleDirectoryReader(
                input_dir=str(source_path),
                recursive=req.recursive,
                required_exts=[".txt", ".md", ".pdf", ".docx"],
                filename_as_id=True,
            ).load_data()
        except ValueError as e:
            # e.g. "No files found in <path>"
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to load documents: {e}")

        if not docs:
            raise HTTPException(status_code=400, detail="No supported documents found")

        collection = self._collection(req.collection, rebuild=req.rebuild)
        vector_store = ChromaVectorStore(chroma_collection=collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        try:
            VectorStoreIndex.from_documents(docs, storage_context=storage_context, show_progress=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Index build failed: {e}")
        return {"status": "ok", "indexed_docs": len(docs), "collection": req.collection}

    def query(self, req: QueryRequest) -> dict:
        collection = self._collection(req.collection, rebuild=False)
        vector_store = ChromaVectorStore(chroma_collection=collection)
        index = VectorStoreIndex.from_vector_store(vector_store=vector_store)

        template = MN_QA_TEMPLATE if _has_cyrillic(req.question) else EN_QA_TEMPLATE
        query_engine = index.as_query_engine(
            similarity_top_k=req.top_k,
            text_qa_template=template,
        )
        try:
            response = query_engine.query(req.question)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Query failed: {e}")
        raw_answer = str(response)
        parsed = _parse_structured_answer(raw_answer)
        sources = []
        max_score = None
        for n in response.source_nodes:
            meta = n.node.metadata or {}
            file_path = meta.get("file_path", "")
            preview = _extract_preview(n.node)
            line_start, line_end = _infer_line_range(file_path, meta, preview)
            score = n.score if isinstance(n.score, (int, float)) else None
            if score is not None:
                max_score = score if max_score is None else max(max_score, score)
            sources.append(
                {
                    "score": score,
                    "file": meta.get("file_name", file_path or "unknown"),
                    "preview": preview,
                    "line_start": line_start,
                    "line_end": line_end,
                }
            )

        # Production-safe guard: refuse confident answers when retrieval context is weak.
        if STRICT_CONTEXT_MODE and (not sources or (max_score is not None and max_score < MIN_SOURCE_SCORE)):
            is_mn = _has_cyrillic(req.question)
            fallback_answer = (
                "Мэдээлэл хүрэлцэхгүй. Энэ асуултад баттай хариулахад контекст сул байна. "
                "Илүү тодорхой лог/эвент мэдээлэл оруулна уу."
                if is_mn
                else "Insufficient data. Retrieved context is too weak for a reliable production-grade answer. "
                "Please provide more specific logs/events."
            )
            fallback_status = "Мэдээлэл хүрэлцэхгүй" if is_mn else "Insufficient data"
            return {
                "answer": fallback_answer,
                "answer_text": fallback_answer,
                "confidence": "Бага" if is_mn else "Low",
                "status": fallback_status,
                "sources": sources,
            }

        return {
            "answer": raw_answer,
            "answer_text": parsed["answer_text"],
            "confidence": parsed["confidence"],
            "status": parsed["status"],
            "sources": sources,
        }


app = FastAPI(title="Local RAG API", version="1.0.0")
service = RAGService()
web_dir = Path(__file__).parent / "web"
ops_dir = Path(__file__).parent / "web_ops"


@app.middleware("http")
async def force_json_utf8_charset(request, call_next):
    response = await call_next(request)
    ctype = response.headers.get("content-type", "")
    if ctype.startswith("application/json") and "charset=" not in ctype.lower():
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def root():
    return RedirectResponse(url="/chat")


@app.post("/index")
def index_docs(req: IndexRequest) -> dict:
    return service.build_index(req)


@app.post("/query")
def query(req: QueryRequest) -> dict:
    return service.query(req)


if web_dir.exists():
    app.mount("/chat", StaticFiles(directory=str(web_dir), html=True), name="chat")


@app.get("/windows-logs/channels")
def windows_log_channels() -> dict:
    return {"channels": WINDOWS_ALLOWED_CHANNELS}


@app.post("/windows-logs/query")
def windows_logs_query(req: WindowsLogQueryRequest) -> dict:
    events = _run_windows_log_query(req)
    return {
        "channel": req.channel,
        "hours_back": req.hours_back,
        "count": len(events),
        "events": events,
    }


@app.post("/windows-logs/analyze")
def windows_logs_analyze(req: WindowsLogAnalyzeRequest) -> dict:
    events = _run_windows_log_query(
        WindowsLogQueryRequest(
            channel=req.channel,
            hours_back=req.hours_back,
            event_ids=req.event_ids,
            levels=req.levels,
            max_events=req.max_events,
        )
    )
    is_mn = _has_cyrillic(req.question)
    system_prompt = DEFAULT_SYSTEM_PROMPT_MN if is_mn else DEFAULT_SYSTEM_PROMPT_EN
    event_context = json.dumps(events[:50], ensure_ascii=False)  # cap prompt size
    user_prompt = (
        f"Question: {req.question}\n\n"
        f"Channel: {req.channel}\n"
        f"Hours back: {req.hours_back}\n"
        "Events (JSON):\n"
        f"{event_context}\n\n"
        "Return production-grade RCA guidance.\n"
        "Use exact sections and bullet points:\n"
        "Root Cause:\n"
        "- ...\n"
        "Evidence:\n"
        "- ...\n"
        "Actions:\n"
        "- ...\n"
        "Risk:\n"
        "- ...\n"
    )
    answer = _llm_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
    sections = _parse_rca_sections(answer)
    return {
        "answer": answer,
        "sections": sections,
        "event_count": len(events),
        "channel": req.channel,
        "hours_back": req.hours_back,
        "events": events[:20],
    }


if ops_dir.exists():
    app.mount("/ops", StaticFiles(directory=str(ops_dir), html=True), name="ops")
