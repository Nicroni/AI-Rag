import os
import re
from pathlib import Path
from typing import Optional

import chromadb
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from llama_index.core import Settings, SimpleDirectoryReader, StorageContext, VectorStoreIndex
from llama_index.core.prompts import PromptTemplate
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.chroma import ChromaVectorStore


MN_QA_TEMPLATE = PromptTemplate(
    "Контекст:\n"
    "---------------------\n"
    "{context_str}\n"
    "---------------------\n"
    "Та бол баримт-шалгалт хатуу мөрддөг Монгол хэлний туслах.\n"
    "Дүрэм:\n"
    "1) Зөвхөн Монгол кириллээр хариул.\n"
    "2) Баталгаатай биш бол \"мэдэхгүй\" эсвэл \"баттай биш\" гэж хэл.\n"
    "3) Зохиомол баримт бүү гарга.\n"
    "4) Товч, давталтгүй, асуултад төвлөрсөн хариул.\n\n"
    "Асуулт: {query_str}\n\n"
    "Хариултын формат:\n"
    "- Хариулт: <1-3 өгүүлбэр>\n"
    "- Итгэлцүүр: <Өндөр|Дунд|Бага>\n"
    "- Төлөв: <Баттай|Баталгаажуулалт шаардлагатай|Мэдээлэл хүрэлцэхгүй>\n"
)

EN_QA_TEMPLATE = PromptTemplate(
    "Context:\n"
    "---------------------\n"
    "{context_str}\n"
    "---------------------\n"
    "You are a strict fact-checking assistant.\n"
    "Rules:\n"
    "1) Do not invent facts.\n"
    "2) If uncertain, say \"unknown\".\n"
    "3) Be concise and avoid repetition.\n\n"
    "Question: {query_str}\n\n"
    "Response format:\n"
    "- Answer: <1-3 sentences>\n"
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
    top_k: int = Field(default=4, ge=1, le=20)


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
        for n in response.source_nodes:
            meta = n.node.metadata or {}
            file_path = meta.get("file_path", "")
            preview = _extract_preview(n.node)
            line_start, line_end = _infer_line_range(file_path, meta, preview)
            sources.append(
                {
                    "score": n.score,
                    "file": meta.get("file_name", file_path or "unknown"),
                    "preview": preview,
                    "line_start": line_start,
                    "line_end": line_end,
                }
            )
        return {
            "answer": raw_answer,
            "answer_text": parsed["answer_text"],
            "confidence": parsed["confidence"],
            "status": parsed["status"],
            "sources": sources,
        }


app = FastAPI(title="Local RAG API", version="1.0.0")
service = RAGService()


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


@app.post("/index")
def index_docs(req: IndexRequest) -> dict:
    return service.build_index(req)


@app.post("/query")
def query(req: QueryRequest) -> dict:
    return service.query(req)
