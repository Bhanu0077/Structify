import os
import re
import shutil
import uuid
import zipfile

import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services.ingest import process_directory, resolve_repo_root
from services.llm import InsightEngine
from services.rag import ContextEngine
from services.session_manifest import read_extract_root, write_manifest

app = FastAPI(title="Structify API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

rag_engine = ContextEngine()
insight_engine = InsightEngine()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class QueryRequest(BaseModel):
    query: str
    session_id: str


class ExplainRequest(BaseModel):
    session_id: str
    filepath: str


def _parse_github_url(url: str) -> tuple[str, str]:
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$",
        url.strip(),
    )
    if not m:
        raise HTTPException(status_code=400, detail="Invalid GitHub repository URL.")
    owner, repo = m.group(1), m.group(2).rstrip("/")
    return owner, repo


def _download_github_zip(owner: str, repo: str) -> bytes:
    for branch in ("main", "master"):
        zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
        try:
            r = requests.get(zip_url, timeout=120)
            if r.status_code == 200:
                return r.content
        except requests.RequestException:
            continue
    raise HTTPException(
        status_code=400,
        detail="Could not download repository archive (check URL and default branch).",
    )


def _ingest_extracted(session_id: str, session_dir: str, extract_dir: str) -> dict:
    repo_root = resolve_repo_root(extract_dir)
    write_manifest(session_dir, repo_root)
    chunks, file_structure = process_directory(repo_root)
    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="No valid source files found in the repository.",
        )
    rag_engine.build_index(session_id, chunks)
    return {
        "status": "success",
        "session_id": session_id,
        "files_indexed": len(chunks),
        "structure": file_structure,
    }


@app.post("/ingest")
async def ingest_repo(
    file: UploadFile | None = File(None),
    github_url: str | None = Form(None),
):
    """Ingest from a ZIP upload or a public GitHub repository URL."""
    has_file = file is not None and file.filename
    has_gh = bool(github_url and github_url.strip())
    if has_file == has_gh:
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one source: ZIP file or github_url.",
        )

    session_id = str(uuid.uuid4())
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    extract_dir = os.path.join(session_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    zip_path = os.path.join(session_dir, "repo.zip")

    if has_file:
        if not file.filename.endswith(".zip"):
            raise HTTPException(status_code=400, detail="Only ZIP files are supported.")
        with open(zip_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    else:
        owner, repo = _parse_github_url(github_url.strip())
        data = _download_github_zip(owner, repo)
        with open(zip_path, "wb") as f:
            f.write(data)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_dir)

    return _ingest_extracted(session_id, session_dir, extract_dir)


@app.get("/sessions/{session_id}/file")
def get_session_file(session_id: str, path: str):
    """Return UTF-8 text for a file path relative to the ingested repo root."""
    session_dir = os.path.join(UPLOAD_DIR, session_id)
    root = read_extract_root(session_dir)
    if not root or not os.path.isdir(root):
        raise HTTPException(status_code=404, detail="Session not found.")

    rel = path.replace("\\", "/").lstrip("/")
    root_abs = os.path.abspath(root)
    full = os.path.abspath(os.path.join(root_abs, rel))
    if full != root_abs and not full.startswith(root_abs + os.sep):
        raise HTTPException(status_code=403, detail="Invalid path.")

    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="File not found.")

    try:
        with open(full, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        raise HTTPException(status_code=500, detail="Could not read file.")

    return {"path": rel, "content": content}


@app.post("/query")
async def handle_query(request: QueryRequest):
    """Trace search: retrieve chunks and return structured flow insight."""
    if not rag_engine.has_index(request.session_id):
        raise HTTPException(status_code=404, detail="Session index not found.")

    relevant_chunks = rag_engine.search(request.session_id, request.query, top_k=8)
    if not relevant_chunks:
        return {
            "summary": "No matching code slices were retrieved for this trace.",
            "key_points": [],
            "flow_steps": [],
            "involved_files": [],
            "relationships": [],
            "end_to_end_diagram": "graph TD\n  A[No matches] --> B[Narrow the trace or re-index]",
            "diagram_code": "graph TD\n  A[No matches] --> B[Narrow the trace or re-index]",
        }

    return insight_engine.generate_trace_insight(request.query, relevant_chunks)


@app.post("/explain")
async def explain_file(request: ExplainRequest):
    """File-level structured insight; content is read from the session workspace."""
    session_dir = os.path.join(UPLOAD_DIR, request.session_id)
    root = read_extract_root(session_dir)
    if not root or not os.path.isdir(root):
        raise HTTPException(status_code=404, detail="Session not found.")

    rel = request.filepath.replace("\\", "/").lstrip("/")
    root_abs = os.path.abspath(root)
    full = os.path.abspath(os.path.join(root_abs, rel))
    if full != root_abs and not full.startswith(root_abs + os.sep):
        raise HTTPException(status_code=403, detail="Invalid path.")

    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="File not found.")

    try:
        with open(full, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        raise HTTPException(status_code=500, detail="Could not read file.")

    return insight_engine.generate_file_insight(rel, content)


@app.get("/")
def health_check():
    return {"status": "ok"}
