"""Reads CSV files into Transactions.

Two kinds of problems are handled differently:

* A problem with the whole file (missing, empty, wrong columns, not text) raises
  InputFileError.
* A problem with one row (bad date, bad amount, wrong column count) is recorded
  as a RowProblem and loading continues, so the user sees every bad row at once
  instead of fixing them one at a time. No row is ever dropped silently.
"""

import csv
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from ledgermatch.models import Transaction

REQUIRED_COLUMNS = ("date", "description", "amount")

# Strict formats. Python's own parsers are more forgiving than we want:
# date.fromisoformat accepts "20260105" and Decimal accepts "1e3" or "NaN".
_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
_AMOUNT_PATTERN = re.compile(r"-?\d+(\.\d+)?")


class InputFileError(Exception):
    """The file as a whole cannot be used. The message is meant for end users."""


@dataclass(frozen=True)
class RowProblem:
    source: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.source}, line {self.line}: {self.message}"


@dataclass
class LoadResult:
    transactions: list[Transaction] = field(default_factory=list)
    problems: list[RowProblem] = field(default_factory=list)


def _parse_date(text: str) -> date | str:
    """Return a date, or an error message string."""
    cleaned = text.strip()
    if _DATE_PATTERN.fullmatch(cleaned):
        try:
            return date.fromisoformat(cleaned)
        except ValueError:
            pass  # right shape, impossible date such as 2026-02-30
    return f"invalid date {text!r}; use YYYY-MM-DD, for example 2026-01-31"


def _parse_amount(text: str) -> Decimal | str:
    """Return a Decimal, or an error message string."""
    cleaned = text.strip()
    if _AMOUNT_PATTERN.fullmatch(cleaned):
        return Decimal(cleaned)
    return (
        f"invalid amount {text!r}; use a plain number such as 12.50 or -3.00 "
        "(no currency symbols, thousands separators, brackets or exponents)"
    )


def load_transactions(path: str | Path) -> LoadResult:
    """Read one CSV file. See the module docstring for error handling."""
    path = Path(path)
    source = str(path)
    try:
        # utf-8-sig removes the invisible marker Excel puts at the start of CSVs.
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return _read(csv.reader(handle, strict=True), source)
    except FileNotFoundError:
        raise InputFileError(f"{source}: file not found.") from None
    except IsADirectoryError:
        raise InputFileError(f"{source}: this is a folder, not a CSV file.") from None
    except PermissionError:
        raise InputFileError(f"{source}: no permission to read this file.") from None
    except UnicodeDecodeError:
        raise InputFileError(
            f"{source}: not readable as UTF-8 text. Is it really a CSV file?"
        ) from None


def _read(reader, source: str) -> LoadResult:
    try:
        header = next(reader, None)
    except csv.Error as exc:
        raise InputFileError(f"{source}: malformed CSV header ({exc}).") from None
    if header is None:
        raise InputFileError(f"{source}: file is empty (no header row).")

    names = [name.strip().lower() for name in header]
    missing = [col for col in REQUIRED_COLUMNS if col not in names]
    if missing:
        raise InputFileError(
            f"{source}: missing required column(s): {', '.join(missing)}. "
            f"Expected header: {','.join(REQUIRED_COLUMNS)}."
        )
    unexpected = [name for name in names if name not in REQUIRED_COLUMNS]
    if unexpected:
        raise InputFileError(
            f"{source}: unexpected column(s): {', '.join(unexpected)}. Version 0.1 "
            f"accepts only {','.join(REQUIRED_COLUMNS)}; extra columns are refused "
            "rather than silently ignored."
        )
    if len(set(names)) != len(names):
        raise InputFileError(f"{source}: duplicate column names in the header.")
    index = {col: names.index(col) for col in REQUIRED_COLUMNS}

    result = LoadResult()
    while True:
        start_line = reader.line_num + 1  # a quoted field can span several lines
        try:
            row = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            raise InputFileError(
                f"{source}, line {start_line}: malformed CSV ({exc})."
            ) from None
        if not row:  # a completely blank line carries no data
            continue
        if len(row) != len(names):
            result.problems.append(
                RowProblem(
                    source, start_line,
                    f"expected {len(names)} columns but found {len(row)}",
                )
            )
            continue

        raw_date, description, raw_amount = (
            row[index["date"]], row[index["description"]], row[index["amount"]],
        )
        parsed_date = _parse_date(raw_date)
        parsed_amount = _parse_amount(raw_amount)
        row_ok = True
        for parsed in (parsed_date, parsed_amount):
            if isinstance(parsed, str):
                result.problems.append(RowProblem(source, start_line, parsed))
                row_ok = False
        if row_ok:
            result.transactions.append(
                Transaction(
                    source=source, line=start_line, date=parsed_date,
                    description=description, amount=parsed_amount,
                    raw_date=raw_date.strip(), raw_amount=raw_amount.strip(),
                )
            )
    return result
