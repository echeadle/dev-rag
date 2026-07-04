"""
Headroom compression wrapper for dev-rag MCP server.
Stub file — implement per planning/headroom-integration-spec.md
"""
# TODO: implement Headroom CCR compression
# Full spec in planning/headroom-integration-spec.md

def compress_text(text: str) -> str:
    """Compress text using Headroom CCR. Falls back to original if unavailable."""
    return text   # stub — returns unchanged until Headroom is wired in


def compression_stats() -> dict:
    """Return session compression statistics."""
    return {"enabled": False, "reason": "not yet implemented"}
