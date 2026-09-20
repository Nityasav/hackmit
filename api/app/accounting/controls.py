"""Deterministic checks over committed records.

This is the home of every rules-based test in the system: three-way matching,
reconciliation differences, duplicate detection, control failures. None of it is a
model's opinion — each check is arithmetic or set logic over supplied records, with
an explanation a person can re-derive by hand.

The checks themselves land in phase 4, alongside the D2 Controls Testing agent that
presents them. The function exists now, and returns nothing, because the alternative
was leaving `reviews.py` importing a module that no longer exists: an endpoint that
500s says "broken", while an endpoint that returns no findings and says why is merely
incomplete. Nothing here fabricates a pass.

Design rules the phase-4 implementation must keep, carried over from the checks this
replaces because they were learned the hard way:

- A check's id names *what the finding is*, never which rows are currently in it.
  A reviewer attaches follow-up to (finding_id, snapshot_id); an id that moves when a
  group gains a row orphans that note and re-presents the finding as new. Derive the
  id from the grouping key, or fix it and let evidence carry membership.
- A passing check is still a finding. "No exact-key duplicate in the supplied
  register" is a statement about what was tested, and it belongs on screen next to
  what it did not test.
- Amounts from different checks are never summed, and an unreconciled difference is
  never described as a loss, a saving or a recovery.
"""

from __future__ import annotations


def checks(records: list[dict], config: dict) -> list[dict]:
    """Every deterministic finding for one snapshot. Empty until phase 4.

    Returns a list of dicts shaped: id, title, role, status
    (pass | attention | gap), explanation, amount_cents, action, origin, review,
    evidence[{source_id, line}].
    """
    return []
