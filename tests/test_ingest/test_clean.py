"""Stage 2 clean tests — synthetic noisy pages, no real book."""
import json

from dev_rag.ingest.clean import clean_document, load_raw, save_cleaned

CONTENT = (
    "Docker networking\n"
    "Docker bridge networks connect containers on the same host. "
    "Each container gets an IP on the bridge, and the docker0 interface "
    "routes traffic between them. Overlay networks extend this across "
    "hosts using VXLAN encapsulation, which is what Swarm mode uses.\n"
    "42\n"
    "Chapter 11: Networking"
)


def page(num, text):
    return {"page_number": num, "text": text, "has_images": False}


def test_blank_page_removed():
    result = clean_document([page(1, "   \n  ")])
    assert result[0].was_removed
    assert result[0].removal_reason == "blank_page"


def test_too_short_page_removed():
    result = clean_document([page(1, "Part II")])
    assert result[0].was_removed
    assert result[0].removal_reason == "too_short"


def test_toc_page_removed():
    toc = "\n".join(
        f"Chapter {i}: Some Topic Here . . . . . . . . . . . . . . {i * 10}"
        for i in range(1, 12)
    )
    result = clean_document([page(1, toc)])
    assert result[0].was_removed
    assert result[0].removal_reason == "table_of_contents"


def test_index_page_removed():
    index = "\n".join(
        f"{word}   {i * 7}"
        for i, word in enumerate(
            ["bridge", "container", "daemon", "engine", "image", "layer",
             "network", "overlay", "registry", "swarm", "volume", "vxlan"], 1)
    )
    result = clean_document([page(1, index)])
    assert result[0].was_removed
    assert result[0].removal_reason == "index_page"


def test_copyright_page_removed():
    text = (
        "Copyright 2023 by the author. All rights reserved. "
        "No part of this publication may be reproduced without permission. "
        "ISBN 978-1-521822-80-8. Printed in the United States."
    )
    result = clean_document([page(1, text)])
    assert result[0].was_removed
    assert result[0].removal_reason == "copyright_page"


def test_content_page_kept_and_cleaned():
    result = clean_document([page(7, CONTENT)])
    p = result[0]
    assert not p.was_removed
    assert "bridge networks connect" in p.text
    # standalone page number line removed
    assert "\n42\n" not in p.text + "\n"
    # short first line (running header) and last line (footer) removed
    assert "Docker networking\n" not in p.text
    assert "Chapter 11: Networking" not in p.text


def test_hyphenation_rejoined():
    text = (
        "Container orchestration platforms manage the lifecycle of contain-\n"
        "erised applications across a cluster of machines, handling schedul-\n"
        "ing, scaling, and recovery when individual nodes fail in production."
    )
    result = clean_document([page(1, text)])
    assert "containerised" in result[0].text
    assert "scheduling" in result[0].text


def test_removed_pages_retained_for_inspection():
    result = clean_document([page(1, ""), page(2, CONTENT)])
    assert len(result) == 2
    assert result[0].was_removed and not result[1].was_removed


def test_save_cleaned_round_trips(tmp_path):
    raw = {
        "source_path": "data/books/tiny-book.pdf",
        "source_type": "pdf",
        "title": "Tiny Book",
        "total_pages": 2,
    }
    pages = clean_document([page(1, ""), page(2, CONTENT)])
    saved = save_cleaned(raw, pages, tmp_path / "cleaned")
    assert saved.name == "tiny-book_cleaned.json"
    data = json.loads(saved.read_text())
    assert data["title"] == "Tiny Book"
    assert data["pages"][0]["was_removed"] is True
    assert data["pages"][1]["was_removed"] is False


def test_load_raw(tmp_path):
    path = tmp_path / "x.json"
    path.write_text(json.dumps({"title": "T", "pages": []}))
    assert load_raw(path)["title"] == "T"
