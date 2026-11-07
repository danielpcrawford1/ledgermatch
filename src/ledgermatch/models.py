"""Plain data types shared by every part of LedgerMatch.

This module has no logic and imports nothing from the rest of the package, so
it can never create a circular dependency.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Transaction:
    """One row from an input file.

    `raw_date` and `raw_amount` keep the text exactly as it appeared in the
    file. Reports print the raw text, so the tool never rewrites your data
    (for example, "10.10" stays "10.10", not "10.1").
    """

    source: str  # which file it came from
    line: int  # line number in that file (where the record starts)
    date: date
    description: str
    amount: Decimal
    raw_date: str
    raw_amount: str


@dataclass(frozen=True)
class Match:
    """A bank transaction paired with a register transaction."""

    bank: Transaction
    register: Transaction
    # True when this pairing was one of several equally valid choices, because
    # the same date and amount appears more than once. See AmbiguousGroup.
    ambiguous: bool = False


@dataclass(frozen=True)
class AmbiguousGroup:
    """A date and amount that appears more than once while also matching.

    Example: the bank shows two 4.50 coffees on 2026-03-04 and the register
    shows one. One bank row matches and one does not, but nothing in the data
    says which. LedgerMatch pairs rows in file order and flags the group so a
    person can review it.
    """

    date: date
    amount: Decimal
    bank_count: int
    register_count: int


@dataclass
class ReconciliationResult:
    """Everything the engine found. Every input row appears exactly once."""

    matches: list[Match] = field(default_factory=list)
    bank_only: list[Transaction] = field(default_factory=list)
    register_only: list[Transaction] = field(default_factory=list)
    ambiguous_groups: dict[tuple[date, Decimal], AmbiguousGroup] = field(
        default_factory=dict
    )
