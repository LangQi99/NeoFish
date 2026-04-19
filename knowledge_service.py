from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

from knowledge_indexer import FaissKnowledgeIndexer

def _now_iso() -> str:
    return datetime.now().isoformat()


def _human_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def _slugify_folder_id(name: str) -> str:
    base = name.strip().lower()
    # Keep letters/numbers/underscore/hyphen and CJK; normalize separators to "_".
    base = re.sub(r"\s+", "_", base)
    base = re.sub(r"[^a-z0-9_\-\u4e00-\u9fff]", "_", base)
    base = re.sub(r"_+", "_", base).strip("_")
    return base or "folder"


class KnowledgeService:
    """Folder-level knowledge base management and lightweight state persistence."""

    def __init__(self, workdir: Path) -> None:
        self.workdir = workdir.resolve()
        self.knowledge_root = (self.workdir / "knowledge").resolve()
        self.meta_root = (self.workdir / ".knowledge").resolve()
        self.state_file = self.meta_root / "state.json"
        self.file_index_file = self.meta_root / "file_index.json"
        self._lock = RLock()

        self.knowledge_root.mkdir(parents=True, exist_ok=True)
        self.meta_root.mkdir(parents=True, exist_ok=True)

        self.state = self._load_state()
        self.file_index = self._load_file_index()
        self.indexer = FaissKnowledgeIndexer(self.meta_root)
        self._save_state()
        self._save_file_index()

    def _load_state(self) -> dict[str, Any]:
        default_state: dict[str, Any] = {
            "selected_folder_ids": [],
            "indexed_folder_ids": [],
            "dirty_folders": [],
            "folder_status": {},
            "folder_display_names": {},
        }
        if not self.state_file.exists():
            return default_state
        try:
            loaded = json.loads(self.state_file.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                return default_state
            default_state.update(loaded)
            for key in (
                "selected_folder_ids",
                "indexed_folder_ids",
                "dirty_folders",
            ):
                if not isinstance(default_state.get(key), list):
                    default_state[key] = []
            if not isinstance(default_state.get("folder_status"), dict):
                default_state["folder_status"] = {}
            if not isinstance(default_state.get("folder_display_names"), dict):
                default_state["folder_display_names"] = {}
            return default_state
        except Exception:
            return default_state

    def _load_file_index(self) -> dict[str, dict[str, Any]]:
        if not self.file_index_file.exists():
            return {}
        try:
            loaded = json.loads(self.file_index_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return loaded
        except Exception:
            pass
        return {}

    def _save_state(self) -> None:
        self.state_file.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _save_file_index(self) -> None:
        self.file_index_file.write_text(
            json.dumps(self.file_index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def refresh_from_disk(self) -> None:
        with self._lock:
            self.state = self._load_state()
            self.file_index = self._load_file_index()
            self.indexer.reload()

    def _folder_path(self, folder_id: str) -> Path:
        path = (self.knowledge_root / folder_id).resolve()
        if not str(path).startswith(str(self.knowledge_root)):
            raise ValueError("Invalid folder_id")
        return path

    def _generate_file_id(self, folder_id: str, rel_path: str) -> str:
        seed = f"{folder_id}:{rel_path}"
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()

    def _sync_file_index_for_folder(self, folder_id: str) -> None:
        folder_path = self._folder_path(folder_id)
        if not folder_path.exists():
            return

        # Remove stale entries for the folder first, then repopulate.
        stale_ids = [
            fid
            for fid, meta in self.file_index.items()
            if meta.get("folder_id") == folder_id
        ]
        for fid in stale_ids:
            self.file_index.pop(fid, None)

        for file_path in folder_path.rglob("*"):
            if not file_path.is_file():
                continue
            rel_path = str(file_path.relative_to(folder_path)).replace("\\", "/")
            file_id = self._generate_file_id(folder_id, rel_path)
            stat = file_path.stat()
            mime_type = (
                mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            )
            self.file_index[file_id] = {
                "folder_id": folder_id,
                "rel_path": rel_path,
                "name": file_path.name,
                "size": int(stat.st_size),
                "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "mime_type": mime_type,
            }

    def _mark_dirty_and_reindex_if_selected(self, folder_id: str) -> None:
        if folder_id not in self.state["selected_folder_ids"]:
            return
        if folder_id not in self.state["dirty_folders"]:
            self.state["dirty_folders"].append(folder_id)
        self.state["folder_status"][folder_id] = "indexing"
        self._sync_file_index_for_folder(folder_id)
        self._rebuild_folder_index(folder_id)

    def _extract_text_for_file(self, file_path: Path, mime_type: str) -> str:
        # First version: index text-like files directly.
        text_like = (
            mime_type.startswith("text/")
            or mime_type in {
                "application/json",
                "application/xml",
                "application/javascript",
            }
            or file_path.suffix.lower() in {
                ".md",
                ".txt",
                ".py",
                ".js",
                ".ts",
                ".tsx",
                ".jsx",
                ".json",
                ".yaml",
                ".yml",
                ".toml",
                ".ini",
                ".cfg",
                ".csv",
                ".html",
                ".css",
                ".sql",
            }
        )
        if not text_like:
            return ""
        try:
            return file_path.read_text(encoding="utf-8")
        except Exception:
            try:
                return file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return ""

    def _rebuild_folder_index(self, folder_id: str) -> None:
        chunks: list[dict[str, Any]] = []
        for file_id, meta in self.file_index.items():
            if meta.get("folder_id") != folder_id:
                continue
            rel_path = str(meta.get("rel_path", ""))
            file_path = self._folder_path(folder_id) / rel_path
            if not file_path.exists():
                continue
            mime_type = str(meta.get("mime_type", "application/octet-stream"))
            text = self._extract_text_for_file(file_path, mime_type)
            if not text.strip():
                continue
            source_path = str(file_path.relative_to(self.workdir)).replace("\\", "/")
            chunks.extend(
                self.indexer.build_chunks_from_text(
                    folder_id=folder_id,
                    file_id=file_id,
                    source_path=source_path,
                    text=text,
                )
            )
        self.indexer.rebuild_folder(folder_id, chunks)
        self.state["folder_status"][folder_id] = "ready"
        if folder_id not in self.state["indexed_folder_ids"]:
            self.state["indexed_folder_ids"].append(folder_id)
        if folder_id in self.state["dirty_folders"]:
            self.state["dirty_folders"].remove(folder_id)

    def list_folders(self) -> list[dict[str, Any]]:
        with self._lock:
            folder_rows: list[dict[str, Any]] = []
            for folder_path in sorted(self.knowledge_root.iterdir(), key=lambda p: p.name):
                if not folder_path.is_dir():
                    continue

                file_count = 0
                total_size = 0
                latest_mtime = 0.0
                for fp in folder_path.rglob("*"):
                    if not fp.is_file():
                        continue
                    file_count += 1
                    stat = fp.stat()
                    total_size += int(stat.st_size)
                    latest_mtime = max(latest_mtime, stat.st_mtime)

                folder_id = folder_path.name
                display_name = self.state["folder_display_names"].get(folder_id, folder_id)
                updated_at = (
                    datetime.fromtimestamp(latest_mtime).isoformat()
                    if latest_mtime > 0
                    else _now_iso()
                )
                folder_rows.append(
                    {
                        "id": folder_id,
                        "name": display_name,
                        "path": str(folder_path.relative_to(self.workdir)).replace("\\", "/"),
                        "file_count": file_count,
                        "updated_at": updated_at,
                        "size_label": _human_size(total_size),
                    }
                )
            return folder_rows

    def create_folder(self, name: str) -> dict[str, Any]:
        with self._lock:
            raw_name = name.strip()
            if not raw_name:
                raise ValueError("Folder name is required")

            base_id = _slugify_folder_id(raw_name)
            folder_id = base_id
            suffix = 1
            while self._folder_path(folder_id).exists():
                suffix += 1
                folder_id = f"{base_id}_{suffix}"

            folder_path = self._folder_path(folder_id)
            folder_path.mkdir(parents=True, exist_ok=False)

            self.state["folder_display_names"][folder_id] = raw_name
            self.state["folder_status"].setdefault(folder_id, "ready")
            self._save_state()

            return {
                "id": folder_id,
                "name": raw_name,
                "path": str(folder_path.relative_to(self.workdir)).replace("\\", "/"),
                "file_count": 0,
                "updated_at": _now_iso(),
                "size_label": "0 B",
            }

    def get_selected(self) -> list[str]:
        with self._lock:
            return list(self.state["selected_folder_ids"])

    def select_folder(self, folder_id: str) -> None:
        with self._lock:
            folder_path = self._folder_path(folder_id)
            if not folder_path.exists():
                raise FileNotFoundError("Folder not found")

            if folder_id not in self.state["selected_folder_ids"]:
                self.state["selected_folder_ids"].append(folder_id)
            self.state["folder_status"][folder_id] = "indexing"
            self._sync_file_index_for_folder(folder_id)
            self._rebuild_folder_index(folder_id)
            self._save_file_index()
            self._save_state()

    def deselect_folder(self, folder_id: str) -> None:
        with self._lock:
            if folder_id in self.state["selected_folder_ids"]:
                self.state["selected_folder_ids"].remove(folder_id)
            if folder_id in self.state["indexed_folder_ids"]:
                self.state["indexed_folder_ids"].remove(folder_id)
            if folder_id in self.state["dirty_folders"]:
                self.state["dirty_folders"].remove(folder_id)
            self.state["folder_status"][folder_id] = "ready"
            # Cleanup vector entries for this folder.
            self.indexer.remove_folder(folder_id)
            stale_ids = [
                fid
                for fid, meta in self.file_index.items()
                if meta.get("folder_id") == folder_id
            ]
            for fid in stale_ids:
                self.file_index.pop(fid, None)
            self._save_file_index()
            self._save_state()

    def upload_files(self, folder_id: str, files: list[tuple[str, bytes, str]]) -> dict[str, Any]:
        with self._lock:
            folder_path = self._folder_path(folder_id)
            if not folder_path.exists():
                raise FileNotFoundError("Folder not found")

            saved_files: list[str] = []
            for filename, data, _content_type in files:
                safe_name = Path(filename).name.strip() or "unnamed_file"
                target_path = folder_path / safe_name
                stem = target_path.stem
                suffix = target_path.suffix
                counter = 1
                while target_path.exists():
                    target_path = folder_path / f"{stem}_{counter}{suffix}"
                    counter += 1
                target_path.write_bytes(data)
                saved_files.append(target_path.name)

            self._mark_dirty_and_reindex_if_selected(folder_id)
            self._save_file_index()
            self._save_state()
            return {
                "saved_count": len(saved_files),
                "saved_files": saved_files,
            }

    def list_files(self, folder_id: str) -> list[dict[str, Any]]:
        with self._lock:
            folder_path = self._folder_path(folder_id)
            if not folder_path.exists():
                raise FileNotFoundError("Folder not found")

            self._sync_file_index_for_folder(folder_id)
            self._save_file_index()

            items: list[dict[str, Any]] = []
            for file_id, meta in self.file_index.items():
                if meta.get("folder_id") != folder_id:
                    continue
                mime_type = str(meta.get("mime_type", "application/octet-stream"))
                preview_url = (
                    f"/knowledge/files/{file_id}/preview"
                    if mime_type.startswith("image/")
                    else None
                )
                items.append(
                    {
                        "id": file_id,
                        "name": meta.get("name", ""),
                        "mime_type": mime_type,
                        "size_label": _human_size(int(meta.get("size", 0))),
                        "updated_at": meta.get("updated_at", _now_iso()),
                        "preview_url": preview_url,
                    }
                )
            items.sort(key=lambda x: str(x["updated_at"]), reverse=True)
            return items

    def _resolve_file_from_index(self, file_id: str) -> tuple[Path, dict[str, Any]]:
        meta = self.file_index.get(file_id)
        if not meta:
            raise FileNotFoundError("File not found")
        folder_id = str(meta.get("folder_id", ""))
        rel_path = str(meta.get("rel_path", ""))
        file_path = self._folder_path(folder_id) / rel_path
        if not file_path.exists():
            # stale index; clean and fail.
            self.file_index.pop(file_id, None)
            self._save_file_index()
            raise FileNotFoundError("File not found")
        return file_path, meta

    def delete_file(self, file_id: str) -> dict[str, Any]:
        with self._lock:
            file_path, meta = self._resolve_file_from_index(file_id)
            folder_id = str(meta.get("folder_id", ""))
            file_path.unlink(missing_ok=True)
            self.file_index.pop(file_id, None)
            self._mark_dirty_and_reindex_if_selected(folder_id)
            self._save_file_index()
            self._save_state()
            return {"ok": True, "folder_id": folder_id}

    def preview_path(self, file_id: str) -> Path:
        with self._lock:
            file_path, meta = self._resolve_file_from_index(file_id)
            mime_type = str(meta.get("mime_type", "application/octet-stream"))
            if not mime_type.startswith("image/"):
                raise ValueError("Preview is only supported for image files")
            return file_path

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "selected_folder_ids": list(self.state["selected_folder_ids"]),
                "indexed_folder_ids": list(self.state["indexed_folder_ids"]),
                "dirty_folders": list(self.state["dirty_folders"]),
                "folder_status": dict(self.state["folder_status"]),
                "index_stats": self.indexer.stats(),
            }

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        with self._lock:
            # Keep multi-instance state consistent (main.py and agent.py each hold a service instance).
            self.state = self._load_state()
            self.file_index = self._load_file_index()
            self.indexer.reload()
            selected = list(self.state["selected_folder_ids"])
            return self.indexer.search(query=query, selected_folders=selected, top_k=top_k)
