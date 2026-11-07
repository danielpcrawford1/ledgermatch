"""Turns a ReconciliationResult into a terminal summary and CSV files.

Nothing here changes the reconciliation. Dates are written as YYYY-MM-DD so
reports look the same whatever format the input used; amounts keep the digits
from the file; and an `original` column holds the complete source row as JSON.
"""

import csv
import json
from decimal import Decimal
from pathlib import Path

from ledgermatch.models import ReconciliationResult, Transaction

REPORT_FILES = ("matched.csv", "bank_only.csv", "register_only.csv")


class OutputExistsError(Exception):
    """Refusing to overwrite existing report files."""


def _total(transactions: list[Transaction]) -> Decimal:
    return sum((t.amount for t in transactions), Decimal(0))


def _fmt(amount: Decimal) -> str:
    return format(amount, "f")


def _note(result: ReconciliationResult, txn: Transaction) -> str:
    group = result.ambiguous_groups.get((txn.date, txn.amount))
    if group is None:
        return ""
    return (
        f"review: bank has {group.bank_count}, register has {group.register_count} "
        "with this date and amount"
    )


def _original(txn: Transaction) -> str:
    """The untouched source row as JSON, so nothing from the input file is lost."""
    return json.dumps(dict(txn.original), ensure_ascii=False)


def _profile_note(name: str) -> str:
    return f"  (profile: {name})" if name else ""


def format_summary(
    result: ReconciliationResult, bank_profile: str = "", register_profile: str = ""
) -> str:
    bank_matched = [m.bank for m in result.matches]
    register_matched = [m.register for m in result.matches]
    bank_rows = len(bank_matched) + len(result.bank_only)
    register_rows = len(register_matched) + len(result.register_only)
    bank_total = _total(bank_matched) + _total(result.bank_only)
    register_total = _total(register_matched) + _total(result.register_only)

    lines = [
        "LedgerMatch reconciliation summary",
        "==================================",
        f"Bank file:      {bank_rows} rows, total {_fmt(bank_total)}"
        f"{_profile_note(bank_profile)}",
        f"Register file:  {register_rows} rows, total {_fmt(register_total)}"
        f"{_profile_note(register_profile)}",
        "",
        f"Matched:            {len(result.matches)} pairs, "
        f"total {_fmt(_total(bank_matched))}",
        f"Only in bank:       {len(result.bank_only)} rows, "
        f"total {_fmt(_total(result.bank_only))}",
        f"Only in register:   {len(result.register_only)} rows, "
        f"total {_fmt(_total(result.register_only))}",
        "",
        "Check: matched + bank-only = bank total; matched + register-only = register "
        "total. Every input row is in exactly one report.",
    ]
    if result.ambiguous_groups:
        lines += ["", "Needs review (same date and amount appears more than once):"]
        for group in result.ambiguous_groups.values():
            lines.append(
                f"  {group.date.isoformat()}  {_fmt(group.amount)}  "
                f"bank {group.bank_count} / register {group.register_count}"
            )
    return "\n".join(lines)


def write_reports(
    result: ReconciliationResult, output_dir: str | Path, force: bool = False
) -> list[Path]:
    """Write the three CSV reports and return their paths.

    Existing report files are never overwritten unless `force` is True.
    """
    output_dir = Path(output_dir)
    paths = [output_dir / name for name in REPORT_FILES]
    existing = [p for p in paths if p.exists()]
    if existing and not force:
        names = ", ".join(str(p) for p in existing)
        raise OutputExistsError(
            f"{names} already exist(s). Choose another folder with -o, or use "
            "--force to overwrite."
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    with paths[0].open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["date", "amount", "bank_description", "register_description",
             "bank_line", "register_line", "review", "bank_original", "register_original"]
        )
        for m in result.matches:
            writer.writerow(
                [m.bank.date.isoformat(), m.bank.amount_text, m.bank.description,
                 m.register.description, m.bank.line, m.register.line,
                 _note(result, m.bank) if m.ambiguous else "",
                 _original(m.bank), _original(m.register)]
            )

    for path, rows in ((paths[1], result.bank_only), (paths[2], result.register_only)):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["date", "description", "amount", "line", "review", "original"])
            for t in rows:
                writer.writerow(
                    [t.date.isoformat(), t.description, t.amount_text, t.line,
                     _note(result, t), _original(t)]
                )
    return paths


def format_validation(label: str, profile_name: str, transactions: list[Transaction]) -> str:
    """One-file check report for --validate-only: counts, date range, control totals.

    Compare these figures with the bank statement or ledger before trusting a
    profile.
    """
    head = f"{label} (profile: {profile_name}): {len(transactions)} transactions"
    if not transactions:
        return head
    money_in = sum((t.amount for t in transactions if t.amount > 0), Decimal(0))
    money_out = sum((t.amount for t in transactions if t.amount < 0), Decimal(0))
    first = min(t.date for t in transactions).isoformat()
    last = max(t.date for t in transactions).isoformat()
    return (
        f"{head}\n  dates {first} to {last}\n"
        f"  money in  {_fmt(money_in)}\n  money out {_fmt(money_out)}\n"
        f"  net       {_fmt(money_in + money_out)}"
    )
