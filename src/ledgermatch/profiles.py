"""Import profiles: how to read one particular CSV layout.

A profile says which columns hold the date, description and amount, how dates
are written, and how debits and credits work. It is plain configuration; it
contains no reading or matching code. Profiles are TOML files (see
docs/PROFILES.md), checked strictly: a misspelt setting is an error, never
silently ignored.
"""

import codecs
import re
import tomllib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


class ProfileError(Exception):
    """A profile is missing, unreadable or invalid. The message is for end users."""


@dataclass(frozen=True)
class Profile:
    name: str
    description: str = ""
    # [file]
    encoding: str = "utf-8-sig"
    delimiter: str = ","
    skip_rows: int = 0  # lines before the header row (report titles, etc.)
    extra_columns: str = "preserve"  # "preserve" keeps them in `original`; "error" refuses
    # [columns]
    date_column: str = "date"
    description_columns: tuple[str, ...] = ("description",)
    amount_column: str | None = "amount"
    debit_column: str | None = None
    credit_column: str | None = None
    # [dates]
    date_format: str = "%Y-%m-%d"
    zero_padded: bool = True
    # [amounts]
    amount_sign: str = "as-is"  # single amount column only: "as-is" or "inverted"
    debit_means: str | None = None  # debit/credit only: "money-out" or "money-in"
    thousands_separator: str = ""
    decimal_separator: str = "."
    currency_symbol: str = ""
    parentheses_negative: bool = False

    @property
    def uses_debit_credit(self) -> bool:
        return self.debit_column is not None

    def mapped_columns(self) -> list[str]:
        """Header names this profile reads, in a stable order."""
        names = [self.date_column, *self.description_columns]
        if self.uses_debit_credit:
            names += [self.debit_column, self.credit_column]
        else:
            names.append(self.amount_column)
        return names


# The original three-column layout, with the original strict rules.
STANDARD = Profile(name="standard", extra_columns="error")
BUILTIN_PROFILES = {"standard": STANDARD}

_ALLOWED = {
    "": {"name", "description", "file", "columns", "dates", "amounts"},
    "file": {"encoding", "delimiter", "skip_rows", "extra_columns"},
    "columns": {"date", "description", "amount", "debit", "credit"},
    "dates": {"format", "zero_padded"},
    "amounts": {
        "amount_sign", "debit_means", "thousands_separator", "decimal_separator",
        "currency_symbol", "parentheses_negative",
    },
}


def _table(data: dict, key: str, where: str) -> dict:
    table = data.get(key, {})
    if not isinstance(table, dict):
        raise ProfileError(f"{where}: [{key}] must be a table.")
    unknown = sorted(set(table) - _ALLOWED[key])
    if unknown:
        raise ProfileError(
            f"{where}: unknown setting(s) in [{key}]: {', '.join(unknown)}. "
            f"Allowed: {', '.join(sorted(_ALLOWED[key]))}."
        )
    return table


def _get(table: dict, key: str, kind: type, default, where: str, section: str):
    value = table.get(key, default)
    # bool is a subclass of int; do not let `true` pass for a number
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise ProfileError(f"{where}: [{section}] {key} must be {kind.__name__}.")
    return value


def _choice(value: str, options: tuple[str, ...], where: str, setting: str) -> str:
    if value not in options:
        raise ProfileError(
            f"{where}: {setting} must be one of {', '.join(repr(o) for o in options)}, "
            f"not {value!r}."
        )
    return value


def _check_date_format(fmt: str, where: str) -> None:
    directives = set(re.findall(r"%(.)", fmt.replace("%%", "")))
    if "y" in directives:
        raise ProfileError(
            f"{where}: date format {fmt!r} uses a two-digit year (%y), which is "
            "ambiguous. Use a four-digit year (%Y)."
        )
    if not ("Y" in directives and "d" in directives and directives & {"m", "b", "B"}):
        raise ProfileError(
            f"{where}: date format {fmt!r} must contain a four-digit year (%Y), a "
            "month (%m, %b or %B) and a day (%d)."
        )
    sample = date(2026, 1, 31)
    try:
        ok = datetime.strptime(sample.strftime(fmt), fmt).date() == sample
    except ValueError:
        ok = False
    if not ok:
        raise ProfileError(f"{where}: date format {fmt!r} is not a usable format.")


def profile_from_dict(data: dict, default_name: str, where: str) -> Profile:
    """Build and validate a Profile from parsed TOML."""
    unknown = sorted(set(data) - _ALLOWED[""])
    if unknown:
        raise ProfileError(f"{where}: unknown setting(s): {', '.join(unknown)}.")
    file_t = _table(data, "file", where)
    cols = _table(data, "columns", where)
    dates = _table(data, "dates", where)
    amts = _table(data, "amounts", where)

    name = _get(data, "name", str, default_name, where, "top level")
    description = _get(data, "description", str, "", where, "top level")

    encoding = _get(file_t, "encoding", str, "utf-8-sig", where, "file")
    try:
        codecs.lookup(encoding)
    except LookupError:
        raise ProfileError(f"{where}: unknown encoding {encoding!r}.") from None
    delimiter = _get(file_t, "delimiter", str, ",", where, "file")
    if len(delimiter) != 1 or delimiter in "\r\n\"":
        raise ProfileError(f"{where}: delimiter must be a single character, not {delimiter!r}.")
    skip_rows = _get(file_t, "skip_rows", int, 0, where, "file")
    if skip_rows < 0:
        raise ProfileError(f"{where}: skip_rows cannot be negative.")
    extra = _choice(_get(file_t, "extra_columns", str, "preserve", where, "file"),
                    ("preserve", "error"), where, "[file] extra_columns")

    if "date" not in cols:
        raise ProfileError(f"{where}: [columns] date is required.")
    date_column = _get(cols, "date", str, "", where, "columns")
    desc = cols.get("description", [])
    if isinstance(desc, str):
        desc = [desc]
    if not isinstance(desc, list) or not all(isinstance(d, str) for d in desc):
        raise ProfileError(f"{where}: [columns] description must be a name or a list of names.")
    amount_col = cols.get("amount")
    debit_col, credit_col = cols.get("debit"), cols.get("credit")
    for label, value in (("amount", amount_col), ("debit", debit_col), ("credit", credit_col)):
        if value is not None and not isinstance(value, str):
            raise ProfileError(f"{where}: [columns] {label} must be a column name.")
    if amount_col is not None and (debit_col is not None or credit_col is not None):
        raise ProfileError(
            f"{where}: use either [columns] amount, or debit and credit, not both."
        )
    if amount_col is None and (debit_col is None or credit_col is None):
        raise ProfileError(
            f"{where}: [columns] needs either amount, or both debit and credit."
        )
    used = [date_column, *desc, *(c for c in (amount_col, debit_col, credit_col) if c)]
    folded = [u.strip().lower() for u in used]
    if "" in folded or len(set(folded)) != len(folded):
        raise ProfileError(
            f"{where}: each [columns] entry must be a non-empty column name used only once."
        )

    date_format = _get(dates, "format", str, "%Y-%m-%d", where, "dates")
    _check_date_format(date_format, where)
    zero_padded = _get(dates, "zero_padded", bool, True, where, "dates")

    sign = _choice(_get(amts, "amount_sign", str, "as-is", where, "amounts"),
                   ("as-is", "inverted"), where, "[amounts] amount_sign")
    debit_means = amts.get("debit_means")
    if debit_col is not None:
        if debit_means is None:
            raise ProfileError(
                f"{where}: [amounts] debit_means is required with debit/credit columns. "
                "Say whether a debit is 'money-out' (bank view) or 'money-in' (a cash "
                "account in your books); LedgerMatch will not guess."
            )
        _choice(debit_means, ("money-out", "money-in"), where, "[amounts] debit_means")
        if "amount_sign" in amts:
            raise ProfileError(f"{where}: amount_sign applies only to a single amount column.")
    elif debit_means is not None:
        raise ProfileError(f"{where}: debit_means applies only with debit/credit columns.")
    thousands = _get(amts, "thousands_separator", str, "", where, "amounts")
    decimal = _get(amts, "decimal_separator", str, ".", where, "amounts")
    _choice(thousands, ("", ",", ".", " ", "'"), where, "[amounts] thousands_separator")
    _choice(decimal, (".", ","), where, "[amounts] decimal_separator")
    if thousands == decimal:
        raise ProfileError(f"{where}: thousands and decimal separators must differ.")
    currency = _get(amts, "currency_symbol", str, "", where, "amounts")
    if re.search(r"[\d\-\s().,]", currency):
        raise ProfileError(f"{where}: currency_symbol must not contain digits, spaces or punctuation.")
    parens = _get(amts, "parentheses_negative", bool, False, where, "amounts")

    return Profile(
        name=name, description=description, encoding=encoding, delimiter=delimiter,
        skip_rows=skip_rows, extra_columns=extra, date_column=date_column,
        description_columns=tuple(desc), amount_column=amount_col,
        debit_column=debit_col, credit_column=credit_col, date_format=date_format,
        zero_padded=zero_padded, amount_sign=sign, debit_means=debit_means,
        thousands_separator=thousands, decimal_separator=decimal,
        currency_symbol=currency, parentheses_negative=parens,
    )


def load_profile(spec: str) -> Profile:
    """Resolve a built-in profile name or the path of a .toml profile file."""
    if spec in BUILTIN_PROFILES:
        return BUILTIN_PROFILES[spec]
    path = Path(spec)
    if not path.is_file():
        raise ProfileError(
            f"profile {spec!r} not found. Use a built-in profile "
            f"({', '.join(BUILTIN_PROFILES)}) or the path of a .toml profile file."
        )
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{spec}: not valid TOML ({exc}).") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise ProfileError(f"{spec}: cannot read profile ({exc}).") from None
    return profile_from_dict(data, default_name=path.stem, where=spec)
