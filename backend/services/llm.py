import json
import os
import re

from huggingface_hub import InferenceClient


def _mer_safe_label(text: str, max_len: int = 36) -> str:
    s = re.sub(r"[\[\]\"#]", "", str(text))
    s = s.replace("\n", " ").strip()
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s or "module"


def _mer_edge_label(text: str, max_len: int = 22) -> str:
    s = _mer_safe_label(text, max_len)
    return s.replace("|", " ")


class InsightEngine:
    def __init__(self):
        self.hf_token = os.environ.get("HF_TOKEN", "").strip()
        self.client = InferenceClient(
            "mistralai/Mistral-7B-Instruct-v0.2",
            token=self.hf_token or None,
        )

    def _call_llm(self, prompt: str) -> str:
        try:
            response = self.client.text_generation(
                prompt,
                max_new_tokens=512,
                temperature=0.1,
                repetition_penalty=1.1,
                return_full_text=False,
            )
            return (response or "").strip()
        except Exception:
            return ""

    def generate_file_insight(self, filepath: str, content: str) -> dict:
        snippet = content[:4000]
        prompt = f"""<s>[INST] You are a senior developer explaining code to a junior. Focus on clarity, structure, and flow. Use simple language and analogies. Avoid unnecessary detail.
Output ONLY valid JSON. No markdown fences.

File: {filepath}
Content:
{snippet}

JSON shape:
{{
  "purpose": "short",
  "key_logic": "short",
  "analogy": "short",
  "end_to_end_diagram": "graph TD\\n  Entry[...] --> ... --> Outcome[...]",
  "diagram_code": "graph LR\\n  optional compact view"
}}
[/INST]"""

        response_text = self._call_llm(prompt)
        try:
            clean = response_text.replace("```json", "").replace("```", "").strip()
            if clean:
                data = json.loads(clean)
                if "diagram_code" not in data or not data["diagram_code"]:
                    data["diagram_code"] = self._file_diagram_fallback(filepath, content)
                e2e = (data.get("end_to_end_diagram") or "").strip()
                if "graph " not in e2e.lower():
                    data["end_to_end_diagram"] = self._file_end_to_end_diagram(filepath, content)
                return {
                    "purpose": data.get("purpose", ""),
                    "key_logic": data.get("key_logic", ""),
                    "analogy": data.get("analogy", ""),
                    "end_to_end_diagram": data["end_to_end_diagram"],
                    "diagram_code": data["diagram_code"],
                }
        except Exception:
            pass

        return {
            "purpose": f"Source module at {filepath}: executable and data definitions for this area of the codebase.",
            "key_logic": self._heuristic_file_logic(content),
            "analogy": "Like a chapter in a manual: it groups related procedures you can run or extend.",
            "end_to_end_diagram": self._file_end_to_end_diagram(filepath, content),
            "diagram_code": self._file_diagram_fallback(filepath, content),
        }

    def _heuristic_file_logic(self, content: str) -> str:
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        preview = lines[:12]
        return "Notable structure: " + "; ".join(preview[:6]) if preview else "No quick structural summary available."

    def _file_diagram_fallback(self, filepath: str, content: str) -> str:
        base = filepath.split("/")[-1]
        symbols = re.findall(
            r"(?:^|\n)\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)|(?:^|\n)\s*class\s+(\w+)",
            content,
        )
        names: list[str] = []
        for a, b in symbols[:6]:
            names.append(a or b)
        if not names:
            return f'graph TD\n  F["{_mer_safe_label(base)}"] --> R["reads/writes local state"]'
        nodes = " --> ".join(f'S{i}["{_mer_safe_label(n)}"]' for i, n in enumerate(names))
        return "graph LR\n  " + nodes

    def _file_end_to_end_diagram(self, filepath: str, content: str) -> str:
        base = filepath.split("/")[-1]
        symbols = re.findall(
            r"(?:^|\n)\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)|(?:^|\n)\s*class\s+(\w+)",
            content,
        )
        names: list[str] = []
        for a, b in symbols[:10]:
            names.append(a or b)
        lines = ["graph TD"]
        e0 = "M0"
        lines.append(
            f'  {e0}["Entry: open {_mer_safe_label(base)}"]'
        )
        prev = e0
        for i, name in enumerate(names):
            nid = f"M{i+1}"
            lines.append(f'  {nid}["{_mer_safe_label(name)}"]')
            lines.append(f"  {prev} --> {nid}")
            prev = nid
        end = "M_END"
        lines.append(f'  {end}["Boundary: exports, IO, side effects"]')
        lines.append(f"  {prev} --> {end}")
        return "\n".join(lines)

    def _build_end_to_end_mermaid(
        self,
        query: str,
        files_ordered: list[str],
        flow_steps: list[str] | None = None,
    ) -> str:
        if not files_ordered:
            return 'graph TD\n  A["No path"] --> B["No files in trace"]'
        q_label = _mer_safe_label(f"Trigger: {query}", 42)
        lines = ["graph TD"]
        start = "P0"
        lines.append(f'  {start}["{_mer_safe_label("Start", 10)}: {q_label}"]')
        prev = start
        steps = flow_steps or []
        for i, fpath in enumerate(files_ordered):
            nid = f"P{i+1}"
            fname = _mer_safe_label(fpath.split("/")[-1], 28)
            path_hint = _mer_safe_label(fpath, 36)
            lines.append(f'  {nid}["{i + 1}. {fname} ({path_hint})"]')
            edge_note = ""
            if i < len(steps):
                raw = re.sub(r"^\d+\.\s*", "", steps[i]).strip()
                edge_note = _mer_edge_label(raw, 20)
            if edge_note:
                lines.append(f'  {prev} -->|"{edge_note}"| {nid}')
            else:
                lines.append(f"  {prev} --> {nid}")
            prev = nid
        end = "P_END"
        lines.append(f'  {end}["{_mer_safe_label("Outcome: response, state, or downstream work", 40)}"]')
        lines.append(f"  {prev} --> {end}")
        return "\n".join(lines)

    def _finalize_trace_payload(self, data: dict, query: str, chunks: list) -> dict:
        data.setdefault("involved_files", [])
        if not data["involved_files"]:
            data["involved_files"] = list(dict.fromkeys(c["filepath"] for c in chunks))
        data.setdefault("relationships", [])
        if not data["relationships"] and len(data["involved_files"]) > 1:
            pairs = list(zip(data["involved_files"], data["involved_files"][1:]))
            data["relationships"] = [
                f"{a} → {b}: sequential coupling in retrieved slices" for a, b in pairs
            ]
        data.setdefault("key_points", [])
        data.setdefault("flow_steps", [])
        dc = (data.get("diagram_code") or "").strip()
        if "graph " not in dc.lower():
            data["diagram_code"] = self._trace_diagram_fallback(chunks)
        e2e = (data.get("end_to_end_diagram") or "").strip()
        if "graph " not in e2e.lower():
            data["end_to_end_diagram"] = self._build_end_to_end_mermaid(
                query, data["involved_files"], data.get("flow_steps")
            )
        return data

    def generate_trace_insight(self, query: str, chunks: list) -> dict:
        context = "\n\n".join(
            [
                f"File: {c['filepath']} (lines {c.get('start_line')}-{c.get('end_line')})\n{c['content'][:800]}"
                for c in chunks
            ]
        )
        prompt = f"""<s>[INST] You are a senior developer explaining code to a junior. Focus on clarity, structure, and flow.
Output ONLY valid JSON. No markdown fences.

Trace: {query}
Slices:
{context[:3200]}

JSON shape:
{{
  "summary": "one short paragraph",
  "key_points": ["...", "..."],
  "flow_steps": ["ordered steps"],
  "involved_files": ["path/relative/to/repo"],
  "relationships": ["file A -> file B: brief link"],
  "end_to_end_diagram": "graph TD\\n  Start[Trigger] --> ModuleA[...] --> ... --> End[Outcome]",
  "diagram_code": "graph TD\\n  optional alternate detail map"
}}
The end_to_end_diagram MUST span trigger to final outcome across all involved_files in order.
[/INST]"""

        response_text = self._call_llm(prompt)
        try:
            clean = response_text.replace("```json", "").replace("```", "").strip()
            if clean:
                data = json.loads(clean)
                return self._finalize_trace_payload(data, query, chunks)
        except Exception:
            pass

        return self._trace_fallback(query, chunks)

    def _trace_diagram_fallback(self, chunks: list) -> str:
        files = []
        seen = set()
        for c in chunks:
            fp = c["filepath"]
            if fp not in seen:
                seen.add(fp)
                files.append(fp)
        if not files:
            return "graph TD\n  A[No data] --> B[Empty]"
        lines = ["graph TD"]
        prev = "T0"
        lines.append(f'  {prev}["{_mer_safe_label("trace")}"]')
        for i, fpath in enumerate(files):
            nid = f"F{i}"
            label = _mer_safe_label(fpath.split("/")[-1])
            lines.append(f'  {prev} --> {nid}["{label}"]')
            prev = nid
        return "\n".join(lines)

    def _trace_fallback(self, query: str, chunks: list) -> dict:
        files_ordered: list[str] = []
        seen: set[str] = set()
        for c in chunks:
            fp = c["filepath"]
            if fp not in seen:
                seen.add(fp)
                files_ordered.append(fp)

        flow_steps = []
        for i, fp in enumerate(files_ordered):
            sym = next(
                (
                    (c.get("symbol") or "").strip()
                    for c in chunks
                    if c["filepath"] == fp and (c.get("symbol") or "").strip()
                ),
                "",
            )
            bit = fp if not sym else f"{fp} (anchor: {sym})"
            flow_steps.append(f"{i + 1}. Inspect {bit}")

        relationships = []
        for a, b in zip(files_ordered, files_ordered[1:]):
            relationships.append(f"{a} → {b}: likely call or data hand-off (from retrieval order)")

        key_points = [
            f"Retrieved {len(chunks)} code slices across {len(files_ordered)} files.",
            f"Trace focus: {_mer_safe_label(query, 80)}",
        ]

        payload = {
            "summary": (
                "Structured trace from retrieved slices (offline summary). "
                "Follow the execution steps and open each file in the center panel for full context."
            ),
            "key_points": key_points,
            "flow_steps": flow_steps or ["No ordered steps available."],
            "involved_files": files_ordered,
            "relationships": relationships,
            "diagram_code": self._trace_diagram_fallback(chunks),
        }
        payload["end_to_end_diagram"] = self._build_end_to_end_mermaid(
            query, files_ordered, payload["flow_steps"]
        )
        return payload
