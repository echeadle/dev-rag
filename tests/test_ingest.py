"""Tests for ingest pipeline — implement as you build ingest.py"""
import pytest
from dev_rag.ingest import chunk_text, content_hash


def test_chunk_text_basic():
    text = "a" * 2500
    chunks = chunk_text(text, chunk_size=1000, overlap=100)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)


def test_chunk_text_overlap():
    text = "hello world " * 200
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    # Adjacent chunks should share content due to overlap
    assert chunks[0][-20:] in chunks[1]


def test_content_hash_deterministic():
    text = "Docker secrets are stored encrypted"
    assert content_hash(text) == content_hash(text)


def test_content_hash_different_for_different_text():
    assert content_hash("text one") != content_hash("text two")
