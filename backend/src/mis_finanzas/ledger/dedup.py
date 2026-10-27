"""Row fingerprints, so overlapping imports of the same account don't duplicate.

A fingerprint is the account, date, amount and the row's occurrence index among rows with
that same date and amount in its file. The description is left out on purpose: two exports
of one account (an Excel movements file and the PDF statement) word and split descriptions
differently, while date and amount always agree.

This is correct because a statement lists every movement of its account for its period.
Two identical purchases on one day get indexes 0 and 1 in every file that holds them, so
the pair is recognized as present when a second file repeats it.
"""

import hashlib
from collections import Counter
from collections.abc import Hashable, Sequence
from datetime import date

FINGERPRINT_VERSION = "v2"


def fingerprint(account_id: int, row_date: date, amount_cents: int, occurrence: int) -> str:
    payload = (
        f"{FINGERPRINT_VERSION}|{account_id}|{row_date.isoformat()}|{amount_cents}|{occurrence}"
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def occurrence_indexes(keys: Sequence[Hashable]) -> list[int]:
    """For each key, how many identical keys came before it: `[a, b, a] -> [0, 0, 1]`."""
    seen: Counter[Hashable] = Counter()
    indexes = []
    for key in keys:
        indexes.append(seen[key])
        seen[key] += 1
    return indexes
