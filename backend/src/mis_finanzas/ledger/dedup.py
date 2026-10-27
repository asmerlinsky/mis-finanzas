"""Row fingerprints, so overlapping imports (PDF + Excel of the same month) don't duplicate.

Two identical purchases on the same day are legitimate, so each fingerprint includes the
row's occurrence index among identical rows in its file. The same pair imported again from
another file gets the same indexes and is recognized as already present.
"""

import hashlib
from collections import Counter
from collections.abc import Sequence
from datetime import date

RowKey = tuple[date, int, str]


def fingerprint(
    account_id: int, row_date: date, amount_cents: int, description_norm: str, occurrence: int
) -> str:
    payload = f"{account_id}|{row_date.isoformat()}|{amount_cents}|{description_norm}|{occurrence}"
    return hashlib.sha256(payload.encode()).hexdigest()


def occurrence_indexes(keys: Sequence[RowKey]) -> list[int]:
    """For each key, how many identical keys came before it: `[a, b, a] -> [0, 0, 1]`."""
    seen: Counter[RowKey] = Counter()
    indexes = []
    for key in keys:
        indexes.append(seen[key])
        seen[key] += 1
    return indexes
