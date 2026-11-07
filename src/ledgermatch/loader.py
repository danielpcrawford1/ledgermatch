"""Reads CSV files into Transactions, following an import profile.

Two kinds of problems are handled differently:

* A problem with the whole file (missing, empty, wrong columns, not text) raises
  InputFileError.
* A problem with one row (bad date, bad amount, wrong column count) is recorded
  as a RowProblem and loading continues, so the user sees every bad row at once
  instead of fixing them one at a time. No row is ever dropped silently.

Every transaction keeps the complete original row in `Transaction.original`.
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path

from ledgermatch.models import Transaction
from ledgermatch.normalize import (
    NormalizationError,
    parse_date,
    parse_debit_credit,
    parse_signed_amount,
)
from ledgermatch.profiles import STANDARD, Profile


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


def load_transactions(path: str | Path, profile: Profile = STANDARD) -> LoadResult:
    """Read one CSV file using `profile`. See the module docstring for error handling."""
    path = Path(path)
    source = str(path)
    try:
        # The default encoding, utf-8-sig, removes the invisible marker Excel
        # puts at the start of CSV files.
        with path.open(newline="", encoding=profile.encoding) as handle:
            for _ in range(profile.skip_rows):  # report titles before the header
                if not handle.readline():
                    break
            reader = csv.reader(handle, delimiter=profile.delimiter, strict=True)
            return _read(reader, source, profile)
    except FileNotFoundError:
        raise InputFileError(f"{source}: file not found.") from None
    except IsADirectoryError:
        raise InputFileError(f"{source}: this is a folder, not a CSV file.") from None
    except PermissionError:
        raise InputFileError(f"{source}: no permission to read this file.") from None
    except UnicodeDecodeError:
        raise InputFileError(
            f"{source}: not readable as {profile.encoding} text (profile "
            f"{profile.name!r}). Is it really a CSV file, and is the profile's "
            "encoding right?"
        ) from None


def _read(reader, source: str, profile: Profile) -> LoadResult:
    offset = profile.skip_rows
    try:
        header = next(reader, None)
    except csv.Error as exc:
        raise InputFileError(f"{source}: malformed CSV header ({exc}).") from None
    if header is None:
        raise InputFileError(f"{source}: file is empty (no header row).")

    names = [name.strip().lower() for name in header]
    wanted = [name.strip().lower() for name in profile.mapped_columns()]
    missing = [orig for orig, key in zip(profile.mapped_columns(), wanted) if key not in names]
    if missing:
        raise InputFileError(
            f"{source}: missing required column(s) for profile {profile.name!r}: "
            f"{', '.join(missing)}. Header found: {', '.join(h.strip() for h in header)}."
        )
    repeated = sorted({key for key in wanted if names.count(key) > 1})
    if repeated:
        raise InputFileError(
            f"{source}: duplicate column name(s) in the header: {', '.join(repeated)}."
        )
    if profile.extra_columns == "error":
        unexpected = [h.strip() for h, n in zip(header, names) if n not in wanted]
        if unexpected:
            raise InputFileError(
                f"{source}: unexpected column(s): {', '.join(unexpected)}. Profile "
                f"{profile.name!r} accepts only: {', '.join(profile.mapped_columns())}. "
                "Extra columns are refused rather than silently ignored; a custom "
                "profile can keep them."
            )
    index = {key: names.index(key) for key in wanted}
    keys = _unique_keys(header)

    def column(row: list[str], name: str) -> str:
        return row[index[name.strip().lower()]]

    result = LoadResult()
    while True:
        start_line = reader.line_num + 1 + offset  # a quoted field can span lines
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
                RowProblem(source, start_line,
                           f"expected {len(names)} columns but found {len(row)}")
            )
            continue

        problems = []
        parsed_date = amount = None
        try:
            parsed_date = parse_date(column(row, profile.date_column), profile)
        except NormalizationError as exc:
            problems.append(str(exc))
        try:
            if profile.uses_debit_credit:
                amount = parse_debit_credit(
                    column(row, profile.debit_column), column(row, profile.credit_column), profile
                )
            else:
                amount = parse_signed_amount(column(row, profile.amount_column), profile)
        except NormalizationError as exc:
            problems.append(str(exc))
        if problems:
            result.problems.extend(RowProblem(source, start_line, p) for p in problems)
            continue

        parts = [column(row, name) for name in profile.description_columns]
        # One description column is kept exactly; several are joined for display
        # (the originals stay in `original`).
        description = parts[0] if len(parts) == 1 else " - ".join(
            p.strip() for p in parts if p.strip()
        )
        result.transactions.append(
            Transaction(
                source=source, line=start_line, date=parsed_date,
                description=description, amount=amount.value,
                raw_date=column(row, profile.date_column).strip(),
                amount_text=amount.text, original=tuple(zip(keys, row)),
            )
        )
    return result


def _unique_keys(header: list[str]) -> list[str]:
    """Header names usable as unique labels, even for blank or repeated headers."""
    keys, seen = [], set()
    for position, name in enumerate(header, start=1):
        key = name.strip() or f"(column {position})"
        if key in seen:
            key = f"{key} (column {position})"
        seen.add(key)
        keys.append(key)
    return keys
