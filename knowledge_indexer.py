from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np

try:
    import faiss  # type: ignore
except Exception as e:  # pragma: no cover
    faiss = None
    _FAISS_IMPORT_ERROR = e
else:  # pragma: no cover
    _FAISS_IMPORT_ERROR = None


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\w\u4e00-\u9fff]+", text.lower())


class FaissKnowledgeIndexer:
    """
    Lightweight FAISS indexer with local deterministic embeddings.

    Notes:
    - Uses hash-based embedding to avoid external embedding service in first stage.
    - Supports folder-level rebuild/remove and query by selected folders.
    """

    def __init__(
        self,
        meta_root: Path,
        dim: int = 384,
        chunk_chars: int = 3200,
        overlap_chars: int = 400,
    ) -> None:
        if faiss is None:
            raise RuntimeError(
                f"FAISS is required but unavailable: {_FAISS_IMPORT_ERROR}"
            )

        self.dim = dim
        self.chunk_chars = max(512, chunk_chars)
        self.overlap_chars = max(64, min(overlap_chars, self.chunk_chars // 2))

        self.snapshot_root = (meta_root / "vector_snapshot").resolve()
        self.snapshot_root.mkdir(parents=True, exist_ok=True)

        self.records_file = self.snapshot_root / "records.json"
        self.vectors_file = self.snapshot_root / "vectors.npy"
        self.index_file = self.snapshot_root / "index.faiss"

        self.records: list[dict[str, Any]] = []
        self.vectors = np.zeros((0, self.dim), dtype=np.float32)
        self.index = faiss.IndexFlatIP(self.dim)

        self._load_snapshot()

    def _embed(self, text: str) -> np.ndarray:
        """
        Deterministic hash embedding (L2-normalized) for local FAISS search.
        """
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = _tokenize(text)
        if not tokens:
            return vec

        for token in tokens:
            h = hashlib.sha1(token.encode("utf-8")).digest()
            bucket = int.from_bytes(h[:4], "little") % self.dim
            sign = -1.0 if (h[4] & 1) else 1.0
            vec[bucket] += sign

        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec

    def _chunk_text(self, text: str) -> list[str]:
        clean = text.strip()
        if not clean:
            return []
        chunks: list[str] = []
        start = 0
        n = len(clean)
        while start < n:
            end = min(n, start + self.chunk_chars)
            chunk = clean[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= n:
                break
            start = max(0, end - self.overlap_chars)
        return chunks

    def _persist_snapshot(self) -> None:
        if len(self.vectors) > 0:
            np.save(self.vectors_file, self.vectors)
        elif self.vectors_file.exists():
            self.vectors_file.unlink(missing_ok=True)

        self.records_file.write_text(
            json.dumps(self.records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        faiss.write_index(self.index, str(self.index_file))

    def _load_snapshot(self) -> None:
        if self.records_file.exists():
            try:
                loaded = json.loads(self.records_file.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    self.records = loaded
            except Exception:
                self.records = []

        if self.vectors_file.exists():
            try:
                arr = np.load(self.vectors_file).astype(np.float32)
                if arr.ndim == 2 and arr.shape[1] == self.dim:
                    self.vectors = arr
            except Exception:
                self.vectors = np.zeros((0, self.dim), dtype=np.float32)

        self._rebuild_faiss_index()

    def reload(self) -> None:
        self.records = []
        self.vectors = np.zeros((0, self.dim), dtype=np.float32)
        self._load_snapshot()

    def _rebuild_faiss_index(self) -> None:
        self.index = faiss.IndexFlatIP(self.dim)
        if len(self.vectors) > 0:
            self.index.add(self.vectors)

    def _remove_folder_internal(self, folder_id: str) -> None:
        if not self.records:
            return
        keep_indices = [
            i for i, rec in enumerate(self.records) if rec.get("folder_id") != folder_id
        ]
        if len(keep_indices) == len(self.records):
            return
        self.records = [self.records[i] for i in keep_indices]
        self.vectors = (
            self.vectors[keep_indices]
            if len(keep_indices) > 0
            else np.zeros((0, self.dim), dtype=np.float32)
        )
        self._rebuild_faiss_index()

    def remove_folder(self, folder_id: str) -> None:
        self._remove_folder_internal(folder_id)
        self._persist_snapshot()

    def rebuild_folder(self, folder_id: str, chunks: list[dict[str, Any]]) -> int:
        # Replace-by-folder strategy.
        self._remove_folder_internal(folder_id)

        if not chunks:
            self._persist_snapshot()
            return 0

        new_records: list[dict[str, Any]] = []
        new_vectors = np.zeros((len(chunks), self.dim), dtype=np.float32)
        for idx, item in enumerate(chunks):
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            vec = self._embed(text)
            new_vectors[idx] = vec
            new_records.append(
                {
                    "folder_id": folder_id,
                    "file_id": item.get("file_id", ""),
                    "chunk_id": item.get("chunk_id", ""),
                    "source_path": item.get("source_path", ""),
                    "chunk_index": item.get("chunk_index", 0),
                    "text": text,
                }
            )

        if new_records:
            valid_count = len(new_records)
            self.vectors = np.vstack([self.vectors, new_vectors[:valid_count]])
            self.records.extend(new_records)

        self._rebuild_faiss_index()
        self._persist_snapshot()
        return len(new_records)

    def build_chunks_from_text(
        self,
        folder_id: str,
        file_id: str,
        source_path: str,
        text: str,
    ) -> list[dict[str, Any]]:
        chunks = self._chunk_text(text)
        out: list[dict[str, Any]] = []
        for idx, chunk in enumerate(chunks):
            out.append(
                {
                    "folder_id": folder_id,
                    "file_id": file_id,
                    "chunk_id": f"{file_id}:{idx}",
                    "source_path": source_path,
                    "chunk_index": idx,
                    "text": chunk,
                }
            )
        return out

    def search(
        self,
        query: str,
        selected_folders: list[str],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        if not selected_folders:
            return []
        if len(self.records) == 0 or self.index.ntotal == 0:
            return []

        q = self._embed(query).reshape(1, -1).astype(np.float32)
        k = max(1, min(top_k * 4, self.index.ntotal))
        scores, ids = self.index.search(q, k)
        selected = set(selected_folders)

        results: list[dict[str, Any]] = []
        for score, idx in zip(scores[0].tolist(), ids[0].tolist()):
            if idx < 0 or idx >= len(self.records):
                continue
            rec = self.records[idx]
            if rec.get("folder_id") not in selected:
                continue
            results.append(
                {
                    "score": float(score),
                    "folder_id": rec.get("folder_id", ""),
                    "file_id": rec.get("file_id", ""),
                    "chunk_id": rec.get("chunk_id", ""),
                    "source_path": rec.get("source_path", ""),
                    "chunk_index": rec.get("chunk_index", 0),
                    "text": rec.get("text", ""),
                }
            )
            if len(results) >= top_k:
                break
        return results

    def stats(self) -> dict[str, Any]:
        folder_counter: dict[str, int] = {}
        for rec in self.records:
            fid = str(rec.get("folder_id", ""))
            folder_counter[fid] = folder_counter.get(fid, 0) + 1
        return {
            "vector_count": int(self.index.ntotal),
            "chunk_count": len(self.records),
            "folder_chunk_counts": folder_counter,
            "dim": self.dim,
            "chunk_chars": self.chunk_chars,
            "overlap_chars": self.overlap_chars,
        }
