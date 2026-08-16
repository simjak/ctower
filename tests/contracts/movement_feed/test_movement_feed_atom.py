"""AC-MOVE-04: strict Atom rendering vectors for the movement stream."""

from __future__ import annotations

import feedparser  # type: ignore[import-untyped]

__all__: tuple[str, ...] = ()

_ATOM_VECTOR = (
    b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <author><name>ctower</name></author>
  <title>ctower movement: ctower</title>
  <id>urn:ctower:movement:ctower</id>
  <link rel="self" href="/v1/projects/ctower/movement.atom?cursor=0&amp;limit=1" />
  <updated>2026-08-09T12:00:00Z</updated>
  <entry>
    <id>urn:uuid:00000000-0000-7000-8000-000000000001</id>
    <title>workflow.changed: capture -&gt; frame</title>
    <updated>2026-08-09T12:00:00Z</updated>
    <link rel="alternate" href="/v1/tickets/00000000-0000-7000-8000-000000000002"""
    b"""/timeline?project_key=ctower" />
  </entry>
</feed>
"""
)


def test_atom_contract_vector_is_validator_clean_with_stable_entry_identity() -> None:
    parsed = feedparser.parse(_ATOM_VECTOR)

    assert parsed.bozo is False
    assert b"<author><name>ctower</name></author>" in _ATOM_VECTOR
    entry = parsed.entries[0]
    assert entry.id == "urn:uuid:00000000-0000-7000-8000-000000000001"
    assert entry.updated == "2026-08-09T12:00:00Z"
    assert any(
        link.rel == "alternate"
        and link.href
        == "/v1/tickets/00000000-0000-7000-8000-000000000002/timeline?project_key=ctower"
        for link in entry.links
    )
    assert "ticket text" not in str(entry)


def test_atom_contract_vector_has_a_self_link_and_no_ticket_text() -> None:
    parsed = feedparser.parse(_ATOM_VECTOR)

    assert parsed.bozo is False
    assert {link.rel: link.href for link in parsed.feed.links} == {
        "self": "/v1/projects/ctower/movement.atom?cursor=0&limit=1"
    }
    assert "ticket text" not in str(parsed)
