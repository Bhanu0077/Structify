# Structify

Minimalist codebase explorer: structure map, trace search, file insights, and Mermaid flow diagrams. The UI reads as a developer tool—structured panels only, no chat surface.

## Stack

- **Backend:** FastAPI, sentence-transformers (`all-MiniLM-L6-v2`), FAISS (file-backed per session), optional Hugging Face Inference (`HF_TOKEN`).
- **Frontend:** Next.js 16, Tailwind CSS 4, Mermaid.js.

## Prerequisites

- Python 3.11+
- Node.js 20+
- (Optional) Hugging Face token for richer text synthesis. Without it, heuristics and retrieval still run; summaries use rule-based fallbacks.

## Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

First embedding download can take a minute. Indexes and uploads are stored under `backend/indexes/` and `backend/uploads/`.

## Frontend

```bash
cd frontend
npm install
# Optional: point to a non-local API
# set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Usage

1. **New workspace:** upload a `.zip` or paste a public `https://github.com/owner/repo` URL.
2. **Structure Map:** open files in the center panel (content is served from the session root).
3. **Trace Search:** use the top field to retrieve slices and see flow summary, steps, involved files, relationships, and a diagram.
4. **File insights:** selecting a file fills the right panel (purpose, key logic, analogy, local flow diagram).

## Docker (Cloud Run–style)

```bash
cd backend
docker build -t structify-api .
docker run -p 8000:8000 -e HF_TOKEN=optional structify-api
```

Use a volume or bucket for `uploads/` and `indexes/` if you need persistence across instances.

## Example ingestion

Zip this repository (or any small Python/TS project), upload it, then trace strings like `ingest`, `FAISS`, or `explain`.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/ingest` | Multipart: `file` (zip) **or** form field `github_url` |
| `GET` | `/sessions/{session_id}/file?path=` | Raw file text |
| `POST` | `/query` | JSON: `{ "query", "session_id" }` |
| `POST` | `/explain` | JSON: `{ "session_id", "filepath" }` |
