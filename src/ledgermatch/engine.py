"""The reconciliation engine: pure logic, no files, no printing.

It takes two lists of Transactions and returns a ReconciliationResult. It
imports only from `models`, so it can be reused by a command line, a web page
or a test without change.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from ledgermatch.models import (
    AmbiguousGroup,
    Match,
    ReconciliationResult,
    Transaction,
)

Key = tuple[date, Decimal]


def _group(transactions: Sequence[Transaction]) -> dict[Key, list[Transaction]]:
    groups: dict[Key, list[Transaction]] = defaultdict(list)
    for txn in transactions:
        groups[(txn.date, txn.amount)].append(txn)
    return groups


def reconcile(
    bank: Sequence[Transaction], register: Sequence[Transaction]
) -> ReconciliationResult:
    """Match bank and register transactions one-to-one.

    Rule: two transactions match only if their dates are equal AND their
    amounts are equal. Descriptions are never compared.

    Duplicates: for each date-and-amount pair, the first bank row is paired
    with the first register row, the second with the second, and so on. Rows
    with no partner are reported as "only in bank" or "only in register".
    A register row is never used twice.

    Whenever the same date and amount appears more than once on either side
    (and at least once on both), the choice of pairing is arbitrary, so the
    group is recorded in `ambiguous_groups` for a person to review.
    """
    bank_groups = _group(bank)
    register_groups = _group(register)

    result = ReconciliationResult()

    for key in sorted(bank_groups.keys() & register_groups.keys()):
        bank_count = len(bank_groups[key])
        register_count = len(register_groups[key])
        if bank_count > 1 or register_count > 1:
            result.ambiguous_groups[key] = AmbiguousGroup(
                date=key[0],
                amount=key[1],
                bank_count=bank_count,
                register_count=register_count,
            )

    # nth occurrence of a key on the bank side pairs with the nth on the register side
    seen: dict[Key, int] = defaultdict(int)
    for txn in bank:
        key = (txn.date, txn.amount)
        position = seen[key]
        seen[key] += 1
        partners = register_groups.get(key, [])
        if position < len(partners):
            result.matches.append(
                Match(txn, partners[position], ambiguous=key in result.ambiguous_groups)
            )
        else:
            result.bank_only.append(txn)

    seen = defaultdict(int)
    for txn in register:
        key = (txn.date, txn.amount)
        position = seen[key]
        seen[key] += 1
        if position >= len(bank_groups.get(key, [])):
            result.register_only.append(txn)

    return result
