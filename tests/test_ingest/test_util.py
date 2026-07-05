from dev_rag.ingest import content_hash


def test_content_hash_deterministic():
    text = "Docker secrets are stored encrypted"
    assert content_hash(text) == content_hash(text)


def test_content_hash_different_for_different_text():
    assert content_hash("text one") != content_hash("text two")
