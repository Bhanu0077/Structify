import json
import os

MANIFEST_NAME = "manifest.json"


def manifest_path(session_dir: str) -> str:
    return os.path.join(session_dir, MANIFEST_NAME)


def write_manifest(session_dir: str, extract_root: str) -> None:
    os.makedirs(session_dir, exist_ok=True)
    with open(manifest_path(session_dir), "w", encoding="utf-8") as f:
        json.dump({"extract_root": os.path.abspath(extract_root)}, f)


def read_extract_root(session_dir: str) -> str | None:
    p = manifest_path(session_dir)
    if not os.path.isfile(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("extract_root")
