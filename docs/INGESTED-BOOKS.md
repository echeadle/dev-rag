# dev-rag — Ingested Books

Authoritative source for this list: `data/dev_rag.db` (`SELECT domain, source_id,
COUNT(*) FROM chunks WHERE status='active' GROUP BY domain, source_id`). Regenerate
by re-running that query — this file is a snapshot, not a live view. Titles/authors/
dates below are cross-referenced from `docs/TODO.md`'s ingest history.

**Total: 12 books, 6,354 chunks, 3 domains** (as of 2026-07-10).

## devops (7 books, 3,797 chunks)

| Title | Author | Chunks | Ingested |
|---|---|---|---|
| Docker Deep Dive | Poulton | 311 | 2026-07-05 |
| A Developer's Essential Guide to Docker Compose | Gkatziouras (Packt, 2023) | 272 | 2026-07-05 |
| Ansible for DevOps | Geerling | 499 | 2026-07-06 |
| Ansible for Real-Life Automation | Madapparambath (Packt, 2022) | 413 | 2026-07-06 |
| Mastering Ansible, 4th Edition | Freeman (Packt, 2021) | 577 | 2026-07-09 |
| Mastering Ubuntu Server, 4th Edition | LaCroix (Packt, 2024) | 1,017 | 2026-07-09 |
| Securing DevOps | Vehent (Manning, 2018) | 708 | 2026-07-09 |

## python (4 books, 1,949 chunks)

| Title | Author | Chunks | Ingested |
|---|---|---|---|
| Five Lines of Code | Clausen | 532 | 2026-07-08 |
| Practices of the Python Pro | Hillard (Manning) | 397 | 2026-07-09 |
| The Art of Unit Testing, 2nd Edition | Osherove (Manning) | 481 | 2026-07-10 |
| Writing Great Specifications | Nicieja (Manning) | 539 | 2026-07-10 |

## ai (1 book, 608 chunks)

| Title | Author | Chunks | Ingested |
|---|---|---|---|
| Unlocking Data with Generative AI and RAG | Bourne (Packt, 2024) | 608 | 2026-07-09 |

## Notes

- **Five Lines of Code** and **The Art of Unit Testing** use `python` domain despite
  not being Python-specific in language (TypeScript and C#/.NET examples,
  respectively) — general software-craft principles apply language-agnostically,
  same bucket as **Writing Great Specifications**.
- Full per-book ingest history, stage-8 verify results, and eval baseline impact are
  in `docs/TODO.md`'s "Active — dev-rag Corpus Building" section.
- To check current live counts instead of this snapshot:
  ```bash
  sqlite3 data/dev_rag.db \
    "SELECT domain, source_id, COUNT(*) FROM chunks WHERE status='active' GROUP BY domain, source_id;"
  ```
  or ask Claude to call the `rag_health` / `list_collections` MCP tools.
