# dev-rag Headroom Integration — Implementation Spec

**Version:** 1.0  
**Date:** June 2026  
**Status:** Ready to implement — after hybrid search and reranker are working

---

## What Headroom Does

Headroom is an open-source context compression library (Apache 2.0, by Tejas
Chopra, Netflix) that reduces the token count of LLM inputs without meaningful
loss of answer quality. It sits between your retrieval pipeline and the model,
compressing tool outputs before they consume context window tokens.

For dev-rag specifically, the problem Headroom solves is this: when Claude Code
calls `search_devops` and gets back 10 chunked passages, those passages may
contain:

- Redundant metadata repeated across every chunk (source path, domain tag,
  page number boilerplate)
- Overlapping content from the sliding-window chunker (the 100-char overlap
  that prevents boundary splits creates literal duplication)
- Contextual scaffolding that the LLM doesn't need verbatim ("In this chapter
  we will discuss...", "As we saw in the previous section...")
- Embedding scores and rank metadata that Claude Code uses internally but
  doesn't need to read as tokens

Headroom's CCR (Content-Compressed Retrieval) algorithm compresses this
redundancy while preserving the semantically dense content. Benchmarks on
RAG workloads show 60–95% token reduction with 95%+ answer accuracy
preservation.

---

## Why This Matters for dev-rag Specifically

The reranker (ADR next step #2) intentionally fetches 50 candidates from
hybrid search before narrowing to 10. Even after narrowing, 10 chunked
passages from technical books can easily consume 4,000–8,000 tokens per
query. Across a multi-turn Claude Code session working through a complex
DevOps problem, that adds up fast.

Headroom is the right complement to the reranker:

```
Reranker:  fewer, better chunks      (quality improvement)
Headroom:  smaller, denser chunks    (efficiency improvement)
```

They address different dimensions of the same problem and are fully
compatible.

---

## Where Headroom Fits in the Architecture

```
FastAPI /search
      │
      ▼
hybrid_search() → reranker → top-10 RankedResult
      │
      ▼
MCP Server: _handle_domain_search()
      │
      ▼
_format_results()          ← current final step
      │
      ▼  [NEW]
_compress_results()        ← Headroom CCR compression
      │
      ▼
types.TextContent          ← returned to Claude Code
```

The integration point is `_format_results()` in `mcp_server.py`. The
formatted markdown string is passed through Headroom before being wrapped
in `TextContent`. This is a single-line change in the handler once the
compression helper is written.

---

## CCR — Content-Compressed Retrieval

CCR is Headroom's key differentiator from simple summarisation. The
distinction matters:

**Simple summarisation** — irreversible. Content is lost. If Claude Code
asks "can you show me the original passage?", there is nothing to show.

**CCR** — reversible. Compressed content is saved to a local store keyed
by a short reference ID. The compressed text sent to Claude Code contains
references like `[ref:a3f2]`. If Claude Code determines it needs the
original, it calls `get_document` with the reference ID and the full
text is retrieved from the local store. Information is never lost — it
is deferred.

For dev-rag this matters because provenance is a first-class concern
(ADR design philosophy: "every retrieved chunk carries its source").
CCR preserves the ability to retrieve the original at any point.

---

## Component Design

### 1. `compress.py` — Headroom wrapper

```python
# mcp/compress.py

import logging
import os
from typing import Optional

log = logging.getLogger("dev-rag-mcp.compress")

# Headroom is optional — if not installed, compression is silently skipped
try:
    from headroom import Compressor, CompressionConfig
    _HEADROOM_AVAILABLE = True
except ImportError:
    _HEADROOM_AVAILABLE = False
    log.info("Headroom not installed — compression disabled. "
             "Install with: uv add headroom")

# Module-level compressor instance — initialised once
_compressor: Optional["Compressor"] = None


def get_compressor() -> Optional["Compressor"]:
    """
    Return the module-level Compressor instance, initialising on first call.
    Returns None if Headroom is not installed or compression is disabled.
    """
    global _compressor

    if not _HEADROOM_AVAILABLE:
        return None

    if os.getenv("DEV_RAG_COMPRESS", "true").lower() == "false":
        return None

    if _compressor is None:
        config = CompressionConfig(
            target_ratio=float(os.getenv("DEV_RAG_COMPRESS_RATIO", "0.4")),
            use_ccr=True,                  # reversible compression
            ccr_store_path=os.getenv(      # where to persist originals
                "DEV_RAG_CCR_STORE",
                ".ccr_store"
            ),
            preserve_code_blocks=True,     # never compress code — it's exact
            preserve_cli_flags=True,       # never compress --flag=value syntax
        )
        _compressor = Compressor(config)
        log.info("Headroom compressor initialised (target ratio: %s)",
                 config.target_ratio)

    return _compressor


def compress_text(text: str) -> str:
    """
    Compress a formatted result string using Headroom CCR.

    If Headroom is not available or compression is disabled, returns
    the original text unchanged. Never raises — compression failure
    falls back to the original text.

    Args:
        text: Formatted markdown string from _format_results()

    Returns:
        Compressed text with CCR reference IDs, or original if unavailable
    """
    compressor = get_compressor()
    if compressor is None:
        return text

    try:
        result = compressor.compress(text)
        original_tokens  = result.original_tokens
        compressed_tokens = result.compressed_tokens
        ratio = 1 - (compressed_tokens / original_tokens) if original_tokens else 0

        log.info(
            "Compressed %d → %d tokens (%.0f%% reduction)",
            original_tokens, compressed_tokens, ratio * 100
        )
        return result.text

    except Exception as exc:
        log.warning("Headroom compression failed, using original: %s", exc)
        return text


def compression_stats() -> dict:
    """
    Return current session compression statistics.
    Useful for the rag_health tool to report compression savings.
    """
    compressor = get_compressor()
    if compressor is None:
        return {"enabled": False, "reason": "not installed or disabled"}

    try:
        stats = compressor.session_stats()
        return {
            "enabled": True,
            "total_original_tokens":    stats.total_original_tokens,
            "total_compressed_tokens":  stats.total_compressed_tokens,
            "total_reduction_pct":      stats.reduction_percentage,
            "queries_compressed":       stats.query_count,
        }
    except Exception:
        return {"enabled": True, "stats": "unavailable"}
```

---

### 2. Changes to `mcp_server.py`

Three small changes — the rest of the file is unchanged:

**Import at top:**
```python
from compress import compress_text, compression_stats
```

**In `_handle_domain_search()` — one line added:**
```python
async def _handle_domain_search(
    domain: str, args: dict
) -> list[types.TextContent]:
    query = args["query"]
    n = min(int(args.get("n_results", 5)), 20)

    try:
        data = await _post("/search", {"query": query, "domain": domain, "n_results": n})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            data = await _post(f"/search/{domain}", {"query": query, "n_results": n})
        else:
            raise

    raw = data.get("results") or data.get("documents")
    results: list = raw if isinstance(raw, list) else ([raw] if raw else [])

    label = {"devops": "DevOps", "python": "Python", "ai": "AI"}.get(
        domain, domain.capitalize()
    )
    header = f"## {label} search: \"{query}\"\n\n"
    body = _format_results(results)

    # ── Headroom compression (new) ──────────────────────────────────────────
    compressed_body = compress_text(body)
    # ───────────────────────────────────────────────────────────────────────

    return [types.TextContent(type="text", text=header + compressed_body)]
```

**In `_handle_search_all()` — same one-line addition:**
```python
    text = _format_results(results)
    compressed_text = compress_text(text)   # ← new

    return [types.TextContent(
        type="text",
        text=f"## Cross-domain search: \"{query}\"\n\n{compressed_text}"
    )]
```

**In `_handle_health()` — add compression stats to health output:**
```python
async def _handle_health() -> list[types.TextContent]:
    try:
        data = await _get("/health")
        status = data.get("status", "unknown")

        # Add compression stats to health report
        data["compression"] = compression_stats()

        text = f"## dev-rag health\n\nStatus: **{status}**\n\n"
        text += f"```json\n{json.dumps(data, indent=2)}\n```"
        return [types.TextContent(type="text", text=text)]
    except httpx.ConnectError:
        return [types.TextContent(
            type="text",
            text=f"**Unreachable** — dev-rag server not responding at {RAG_BASE_URL}"
        )]
```

---

### 3. Configuration via environment variables

All Headroom settings are controlled via environment variables — no code
changes needed to tune compression behaviour:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEV_RAG_COMPRESS` | `true` | Set to `false` to disable completely |
| `DEV_RAG_COMPRESS_RATIO` | `0.4` | Target compression ratio (0.4 = 60% reduction) |
| `DEV_RAG_CCR_STORE` | `.ccr_store` | Directory for CCR original storage |

Pass these via the `claude mcp add` command:

```bash
claude mcp add --transport stdio dev-rag \
  --env DEV_RAG_BASE_URL=http://localhost:8000 \
  --env DEV_RAG_COMPRESS=true \
  --env DEV_RAG_COMPRESS_RATIO=0.4 \
  -- python /path/to/mcp/mcp_server.py
```

Or in `~/.claude.json`:

```json
{
  "mcpServers": {
    "dev-rag": {
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/mcp/mcp_server.py"],
      "env": {
        "DEV_RAG_BASE_URL": "http://localhost:8000",
        "DEV_RAG_COMPRESS": "true",
        "DEV_RAG_COMPRESS_RATIO": "0.4"
      }
    }
  }
}
```

---

### 4. pyproject.toml addition

```toml
[project.optional-dependencies]
compress = [
    "headroom>=0.3.0",
]
```

Headroom is an optional dependency — the MCP server works without it.
Install only when you're ready to enable compression:

```bash
uv add --optional compress headroom
# or simply:
uv add headroom
```

---

### 5. Tests

```python
# tests/test_compress.py

import os
import pytest
from unittest.mock import MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

SAMPLE_TEXT = """### [1] docker-deep-dive.pdf  `devops`  (score: 0.923)

Docker secrets provide a mechanism for securely storing sensitive data
such as passwords, tokens, and SSH keys. Unlike environment variables,
secrets are stored encrypted and only exposed to containers that have
been explicitly granted access.

---

### [2] docker-security.pdf  `devops`  (score: 0.887)

Running containers as root is a security risk. The recommended approach
is to use the USER directive in your Dockerfile to run as a non-root user.
"""


# ── compress_text() — Headroom available ─────────────────────────────────────

def test_compress_text_returns_string_when_headroom_available():
    mock_result = MagicMock()
    mock_result.text = "compressed output"
    mock_result.original_tokens = 200
    mock_result.compressed_tokens = 80

    mock_compressor = MagicMock()
    mock_compressor.compress.return_value = mock_result

    with patch("compress.get_compressor", return_value=mock_compressor):
        from compress import compress_text
        result = compress_text(SAMPLE_TEXT)

    assert result == "compressed output"


def test_compress_text_calls_compressor_with_full_text():
    mock_result = MagicMock()
    mock_result.text = "compressed"
    mock_result.original_tokens = 100
    mock_result.compressed_tokens = 40

    mock_compressor = MagicMock()
    mock_compressor.compress.return_value = mock_result

    with patch("compress.get_compressor", return_value=mock_compressor):
        from compress import compress_text
        compress_text(SAMPLE_TEXT)

    mock_compressor.compress.assert_called_once_with(SAMPLE_TEXT)


# ── compress_text() — graceful fallback ──────────────────────────────────────

def test_compress_text_returns_original_when_headroom_none():
    with patch("compress.get_compressor", return_value=None):
        from compress import compress_text
        result = compress_text(SAMPLE_TEXT)

    assert result == SAMPLE_TEXT


def test_compress_text_falls_back_on_exception():
    mock_compressor = MagicMock()
    mock_compressor.compress.side_effect = RuntimeError("compression error")

    with patch("compress.get_compressor", return_value=mock_compressor):
        from compress import compress_text
        result = compress_text(SAMPLE_TEXT)

    # Should return original text, not raise
    assert result == SAMPLE_TEXT


def test_compress_text_handles_empty_string():
    with patch("compress.get_compressor", return_value=None):
        from compress import compress_text
        result = compress_text("")

    assert result == ""


# ── get_compressor() — environment controls ───────────────────────────────────

def test_compression_disabled_via_env(monkeypatch):
    monkeypatch.setenv("DEV_RAG_COMPRESS", "false")

    # Reset module-level state
    import compress
    compress._compressor = None

    with patch("compress._HEADROOM_AVAILABLE", True):
        result = compress.get_compressor()

    assert result is None


def test_compression_enabled_by_default(monkeypatch):
    monkeypatch.delenv("DEV_RAG_COMPRESS", raising=False)

    import compress
    compress._compressor = None

    mock_compressor_cls = MagicMock()
    mock_instance = MagicMock()
    mock_compressor_cls.return_value = mock_instance

    with patch("compress._HEADROOM_AVAILABLE", True), \
         patch("compress.Compressor", mock_compressor_cls):
        result = compress.get_compressor()

    assert result is mock_instance


# ── compression_stats() ───────────────────────────────────────────────────────

def test_compression_stats_when_disabled():
    with patch("compress.get_compressor", return_value=None):
        from compress import compression_stats
        stats = compression_stats()

    assert stats["enabled"] is False


def test_compression_stats_when_enabled():
    mock_stats = MagicMock()
    mock_stats.total_original_tokens   = 10000
    mock_stats.total_compressed_tokens = 4000
    mock_stats.reduction_percentage    = 60.0
    mock_stats.query_count             = 12

    mock_compressor = MagicMock()
    mock_compressor.session_stats.return_value = mock_stats

    with patch("compress.get_compressor", return_value=mock_compressor):
        from compress import compression_stats
        stats = compression_stats()

    assert stats["enabled"] is True
    assert stats["total_original_tokens"]   == 10000
    assert stats["total_compressed_tokens"] == 4000
    assert stats["queries_compressed"]      == 12
```

---

## New Files Summary

```
dev-rag/
├── mcp/
│   ├── mcp_server.py    # MODIFIED — import compress, 3 small additions
│   └── compress.py      # NEW — Headroom wrapper with graceful fallback
└── tests/
    └── test_compress.py # NEW — 10 tests, all mocked (no Headroom install needed)
```

---

## Implementation Order

1. **Install Headroom:** `uv add headroom`
2. **Run smoke test against real library (OBS-008):**
   ```python
   from headroom import Compressor, CompressionConfig
   c = Compressor(CompressionConfig(target_ratio=0.4, use_ccr=True,
                  preserve_code_blocks=True, preserve_cli_flags=True))
   result = c.compress("Docker secrets store sensitive data securely.")
   print(result.text, result.original_tokens, result.compressed_tokens)
   print(c.session_stats())
   ```
   Confirm the constructor arguments, result attributes (`text`,
   `original_tokens`, `compressed_tokens`), and `session_stats()` all
   exist before writing `compress.py`. If the API differs, update the
   spec before proceeding. The mocked tests will pass regardless —
   only the live smoke test reveals real API mismatches.
3. **Implement `compress.py`** — run its tests in isolation (all mocked,
   Headroom does not need to be importable to pass tests)
4. **Add `from compress import compress_text, compression_stats`** to
   `mcp_server.py`
5. **Add `compress_text()` calls** in `_handle_domain_search()`,
   `_handle_search_all()`, and compression stats to `_handle_health()`
6. **Run full test suite** — all existing tests + 10 new compress tests
7. **Test live** — run a `search_devops` query from Claude Code and check
   the `rag_health` output for compression stats

---

## Tuning the Compression Ratio

The `DEV_RAG_COMPRESS_RATIO` setting (default `0.4`) controls how
aggressively Headroom compresses. Start conservative and tighten if needed:

| Ratio | Token reduction | Risk |
|-------|----------------|------|
| `0.6` | ~40% | Low — light compression, maximum safety |
| `0.4` | ~60% | Medium — good default for technical content |
| `0.2` | ~80% | Higher — watch for quality degradation on dense technical passages |

For the DevOps and Python corpora, which contain code blocks and CLI flags
that must not be compressed, `0.4` is the recommended starting point.
The `preserve_code_blocks=True` and `preserve_cli_flags=True` config options
ensure those sections are never touched regardless of the ratio setting.

After a week of real usage, check `rag_health` for session stats:

```
compression:
  enabled: true
  total_original_tokens: 45230
  total_compressed_tokens: 18092
  total_reduction_pct: 60.0
  queries_compressed: 47
```

If answer quality feels degraded, raise the ratio to `0.5` or `0.6`.
If token savings are the priority and quality is holding, try `0.3`.

---

## Relationship to Prompt Caching

Headroom and Anthropic prompt caching solve different problems and are
complementary:

| | Headroom | Prompt caching |
|--|----------|---------------|
| **Best for** | Dynamic content (RAG chunks, tool outputs) | Fixed prefixes (system prompts, static context) |
| **Mechanism** | Compresses content before sending | Caches the KV computation server-side |
| **Savings** | Fewer tokens sent | Fewer tokens computed |
| **Applies to** | Every query | Repeated identical prefixes only |

For dev-rag, RAG output is dynamic by definition — different queries return
different chunks. Headroom is the right tool. If dev-rag ever gains a large
fixed system prompt, prompt caching becomes relevant for that prefix.

---

## Distinction from prompt caching (ADR reference)

This is recorded in ADR-009 in `DEV-RAG-ARCHITECTURE.md`. The implementation
here is the concrete realisation of that decision.

---

*Add this document to `planning/` alongside `hybrid-search-spec.md`,
`reranker-spec.md`, and `rag-document-update-strategy.md`.*
