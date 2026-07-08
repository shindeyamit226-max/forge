"""
Semantic Code Indexer — embeddings-based code search and understanding.
Indexes the codebase for fast semantic search using TF-IDF + BM25
(no external embedding service required — runs 100% locally).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class IndexedChunk:
    """A chunk of code with metadata for search."""
    id: str
    file: str
    start_line: int
    end_line: int
    content: str
    symbols: list[str] = field(default_factory=list)
    language: str = ""
    chunk_type: str = ""  # function, class, module, docstring
    imports: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    tf: dict[str, float] = field(default_factory=dict)  # term frequency
    bm25_score: float = 0.0

    @property
    def lines(self) -> int:
        return self.end_line - self.start_line + 1


@dataclass
class SearchResult:
    """A search result with relevance score."""
    chunk: IndexedChunk
    score: float
    match_reasons: list[str] = field(default_factory=list)


# Common stop words to filter out
STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "s", "t",
    "just", "don", "now", "and", "but", "or", "if", "while", "this",
    "that", "these", "those", "it", "its", "self", "return", "def",
    "class", "import", "from", "true", "false", "none", "null",
}


def tokenize(text: str) -> list[str]:
    """Tokenize text into searchable tokens."""
    # Split on non-alphanumeric, keep camelCase parts
    tokens = []

    # Split camelCase
    text = re.sub(r'([a-z])([A-Z])', r'\1_\2', text)
    text = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', text)

    # Split on non-alphanumeric
    for token in re.split(r'[^a-zA-Z0-9_]', text):
        token = token.lower().strip()
        if len(token) > 1 and token not in STOP_WORDS:
            tokens.append(token)
            # Also add subtokens for snake_case
            if "_" in token:
                for sub in token.split("_"):
                    if len(sub) > 1 and sub not in STOP_WORDS:
                        tokens.append(sub)

    return tokens


class CodeIndexer:
    """
    Indexes codebase for fast semantic search.
    Uses TF-IDF + BM25 ranking — no external services needed.
    """

    def __init__(self, chunk_size: int = 60, overlap: int = 10):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.chunks: list[IndexedChunk] = []
        self.idf: dict[str, float] = {}  # inverse document frequency
        self.file_hashes: dict[str, str] = {}  # file content hashes for cache
        self._indexed_files: set[str] = set()

    def index_directory(self, root: str, extensions: Optional[set[str]] = None) -> int:
        """Index all code files in a directory."""
        from .context import IGNORE_DIRS, CODE_EXTENSIONS

        if extensions is None:
            extensions = CODE_EXTENSIONS

        root_path = Path(root)
        files_indexed = 0

        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]

            for fname in filenames:
                fpath = Path(dirpath) / fname
                ext = fpath.suffix.lower()

                if ext not in extensions:
                    continue

                rel_path = str(fpath.relative_to(root_path))

                # Check if file changed (cache)
                try:
                    content = fpath.read_text(errors="replace")
                except Exception:
                    continue

                content_hash = hashlib.md5(content.encode()).hexdigest()
                if self.file_hashes.get(rel_path) == content_hash:
                    continue

                self.file_hashes[rel_path] = content_hash

                # Remove old chunks for this file
                self.chunks = [c for c in self.chunks if c.file != rel_path]

                # Index the file
                self._index_file(content, rel_path, ext)
                files_indexed += 1

        # Recalculate IDF
        self._calculate_idf()

        return files_indexed

    def _index_file(self, content: str, filepath: str, ext: str) -> None:
        """Index a single file."""
        lines = content.splitlines()
        lang = ext.lstrip(".")

        # Try to chunk by functions/classes first
        from .ast_editor import get_parser, parse_file
        parser = get_parser(filepath)

        if parser:
            try:
                symbols = parser.parse(content, filepath)
                if symbols:
                    self._index_by_symbols(content, filepath, lang, symbols, lines)
                    return
            except Exception:
                pass

        # Fallback: chunk by fixed-size windows
        self._index_by_lines(filepath, lang, lines)

    def _index_by_symbols(
        self, content: str, filepath: str, lang: str,
        symbols: list, lines: list[str],
    ) -> None:
        """Index file chunks based on code symbols."""
        chunked_lines = set()

        for sym in symbols:
            if sym.kind in ("import", "variable"):
                continue

            start = max(0, sym.line - 1 - self.overlap)
            end = min(len(lines), sym.end_line + self.overlap)

            chunk_content = "\n".join(lines[start:end])
            if not chunk_content.strip():
                continue

            chunk_id = f"{filepath}:{sym.name}:{sym.line}"

            # Extract imports from file
            imports = [s.name for s in symbols if s.kind == "import"]

            tokens = tokenize(chunk_content + " " + sym.name + " " + sym.qualified_name)
            tf = self._compute_tf(tokens)

            self.chunks.append(IndexedChunk(
                id=chunk_id,
                file=filepath,
                start_line=start + 1,
                end_line=end,
                content=chunk_content,
                symbols=[sym.qualified_name],
                language=lang,
                chunk_type=sym.kind,
                imports=imports,
                tokens=tokens,
                tf=tf,
            ))

            for i in range(start, end):
                chunked_lines.add(i)

        # Index remaining lines as module-level code
        remaining = [i for i in range(len(lines)) if i not in chunked_lines]
        if remaining:
            # Group consecutive remaining lines
            groups = self._group_consecutive(remaining)
            for group in groups[:5]:  # Limit module-level chunks
                start = group[0]
                end = group[-1] + 1
                chunk_content = "\n".join(lines[start:end])
                if len(chunk_content.strip()) < 20:
                    continue

                chunk_id = f"{filepath}:module:{start}"
                tokens = tokenize(chunk_content)
                tf = self._compute_tf(tokens)

                self.chunks.append(IndexedChunk(
                    id=chunk_id,
                    file=filepath,
                    start_line=start + 1,
                    end_line=end,
                    content=chunk_content,
                    language=lang,
                    chunk_type="module",
                    tokens=tokens,
                    tf=tf,
                ))

    def _index_by_lines(self, filepath: str, lang: str, lines: list[str]) -> None:
        """Index file by fixed-size line chunks with overlap."""
        i = 0
        while i < len(lines):
            end = min(i + self.chunk_size, len(lines))
            chunk_content = "\n".join(lines[i:end])

            if chunk_content.strip():
                chunk_id = f"{filepath}:lines:{i}"
                tokens = tokenize(chunk_content)
                tf = self._compute_tf(tokens)

                self.chunks.append(IndexedChunk(
                    id=chunk_id,
                    file=filepath,
                    start_line=i + 1,
                    end_line=end,
                    content=chunk_content,
                    language=lang,
                    chunk_type="block",
                    tokens=tokens,
                    tf=tf,
                ))

            i += self.chunk_size - self.overlap

    def _calculate_idf(self) -> None:
        """Calculate inverse document frequency for all terms."""
        n = len(self.chunks)
        if n == 0:
            return

        # Count document frequency
        df = Counter()
        for chunk in self.chunks:
            unique_tokens = set(chunk.tokens)
            for token in unique_tokens:
                df[token] += 1

        # IDF = log(N / df)
        self.idf = {}
        for token, count in df.items():
            self.idf[token] = math.log((n - count + 0.5) / (count + 0.5) + 1)

    @staticmethod
    def _compute_tf(tokens: list[str]) -> dict[str, float]:
        """Compute term frequency (normalized)."""
        if not tokens:
            return {}
        counter = Counter(tokens)
        max_count = max(counter.values())
        return {t: c / max_count for t, c in counter.items()}

    @staticmethod
    def _group_consecutive(nums: list[int]) -> list[list[int]]:
        """Group consecutive numbers."""
        if not nums:
            return []
        groups = [[nums[0]]]
        for n in nums[1:]:
            if n == groups[-1][-1] + 1:
                groups[-1].append(n)
            else:
                groups.append([n])
        return groups

    def search(
        self,
        query: str,
        top_k: int = 10,
        language: Optional[str] = None,
        chunk_type: Optional[str] = None,
        file_filter: Optional[str] = None,
    ) -> list[SearchResult]:
        """
        Semantic search using BM25 ranking.

        BM25(k1=1.5, b=0.75) — the gold standard for text retrieval.
        """
        if not self.chunks:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        k1 = 1.5
        b = 0.75
        avgdl = sum(len(c.tokens) for c in self.chunks) / len(self.chunks)

        results = []

        for chunk in self.chunks:
            # Apply filters
            if language and chunk.language != language:
                continue
            if chunk_type and chunk.chunk_type != chunk_type:
                continue
            if file_filter and file_filter not in chunk.file:
                continue

            # BM25 scoring
            score = 0.0
            dl = len(chunk.tokens)
            match_reasons = []

            for qt in query_tokens:
                if qt not in chunk.tf:
                    continue

                tf = chunk.tf[qt]
                idf = self.idf.get(qt, 0)

                # BM25 formula
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * dl / avgdl)
                term_score = idf * numerator / denominator
                score += term_score

                match_reasons.append(f"term '{qt}' (tf={tf:.2f}, idf={idf:.2f})")

            # Boost for exact symbol matches
            query_lower = query.lower()
            for sym in chunk.symbols:
                if query_lower in sym.lower():
                    score *= 2.0
                    match_reasons.append(f"symbol match: {sym}")
                if sym.lower().startswith(query_lower):
                    score *= 1.5

            # Boost for matching chunk type
            if chunk_type and chunk.chunk_type == chunk_type:
                score *= 1.2

            # Boost for shorter, more focused chunks
            if dl < 100:
                score *= 1.1

            if score > 0:
                results.append(SearchResult(
                    chunk=chunk,
                    score=score,
                    match_reasons=match_reasons,
                ))

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def search_by_symbol(self, name: str) -> list[SearchResult]:
        """Search for a specific symbol by name."""
        results = []
        name_lower = name.lower()

        for chunk in self.chunks:
            for sym in chunk.symbols:
                if sym.lower() == name_lower or sym.lower().endswith(f".{name_lower}"):
                    results.append(SearchResult(
                        chunk=chunk,
                        score=100.0,
                        match_reasons=[f"exact symbol: {sym}"],
                    ))
                    break
                elif name_lower in sym.lower():
                    results.append(SearchResult(
                        chunk=chunk,
                        score=50.0,
                        match_reasons=[f"partial symbol: {sym}"],
                    ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:10]

    @property
    def stats(self) -> dict:
        """Index statistics."""
        files = set(c.file for c in self.chunks)
        langs = Counter(c.language for c in self.chunks)
        return {
            "total_chunks": len(self.chunks),
            "total_files": len(files),
            "languages": dict(langs.most_common(10)),
            "unique_terms": len(self.idf),
        }
