"""Turns the text of a date or amount cell into an exact value.

Pure functions, no file access. Every function either returns a value or raises
NormalizationError with a message fit to show a user. Nothing is guessed: text
that does not fit the profile exactly is rejected.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from ledgermatch.profiles import Profile


class NormalizationError(Exception):
    """A cell does not fit the profile. The message is for end users."""


@dataclass(frozen=True)
class Amount:
    value: Decimal
    text: str  # plain signed text with the file's own digits, e.g. "-1800.50"


def parse_date(text: str, profile: Profile) -> date:
    cleaned = text.strip()
    example = date(2026, 1, 31).strftime(profile.date_format)
    message = (
        f"invalid date {text!r}; this profile expects {profile.date_format} "
        f"(for example {example})"
    )
    try:
        parsed = datetime.strptime(cleaned, profile.date_format)
    except ValueError:
        raise NormalizationError(message) from None
    # strptime is lenient ("2026-1-5" passes "%Y-%m-%d"); insist on exact padding
    # unless the profile says the file does not pad.
    if profile.zero_padded and parsed.strftime(profile.date_format).lower() != cleaned.lower():
        raise NormalizationError(
            message + "; if this file writes dates without leading zeros, set "
            "zero_padded = false in the profile"
        )
    return parsed.date()


def _describe_amount_rules(profile: Profile) -> str:
    parts = ["a plain number such as 12.50 or -3.00"]
    if profile.thousands_separator:
        parts.append(f"thousands separator {profile.thousands_separator!r}")
    if profile.decimal_separator != ".":
        parts.append(f"decimal separator {profile.decimal_separator!r}")
    if profile.currency_symbol:
        parts.append(f"currency symbol {profile.currency_symbol!r}")
    if profile.parentheses_negative:
        parts.append("(brackets) for negatives")
    return parts[0] + (" with " + ", ".join(parts[1:]) if len(parts) > 1 else "")


def _parse_number(text: str, profile: Profile) -> tuple[bool, str]:
    """Return (is_negative, plain unsigned digits such as '1800.50')."""
    cleaned = text.strip()
    bad = NormalizationError(
        f"invalid amount {text!r}; expected {_describe_amount_rules(profile)}"
    )
    negative = False
    if profile.parentheses_negative and cleaned.startswith("(") and cleaned.endswith(")"):
        negative = True
        cleaned = cleaned[1:-1].strip()
    if cleaned.startswith("-"):
        if negative:
            raise bad  # "(-5)" is contradictory
        negative = True
        cleaned = cleaned[1:].lstrip()
    if profile.currency_symbol and cleaned.startswith(profile.currency_symbol):
        cleaned = cleaned[len(profile.currency_symbol):].lstrip()
        if cleaned.startswith("-") and not negative:  # "$-5"
            negative = True
            cleaned = cleaned[1:].lstrip()

    dec = re.escape(profile.decimal_separator)
    if profile.thousands_separator:
        thou = re.escape(profile.thousands_separator)
        integer = rf"(?:\d{{1,3}}(?:{thou}\d{{3}})+|\d+)"
    else:
        integer = r"\d+"
    if not re.fullmatch(rf"{integer}(?:{dec}\d+)?", cleaned):
        raise bad
    if profile.thousands_separator:
        cleaned = cleaned.replace(profile.thousands_separator, "")
    return negative, cleaned.replace(profile.decimal_separator, ".")


def _make_amount(negative: bool, digits: str) -> Amount:
    value = Decimal(digits)
    if value == 0:
        negative = False  # no "negative zero"
    return Amount(-value if negative else value, ("-" if negative else "") + digits)


def parse_signed_amount(text: str, profile: Profile) -> Amount:
    """A single amount column. Positive means money in unless the profile inverts it."""
    negative, digits = _parse_number(text, profile)
    if profile.amount_sign == "inverted":
        negative = not negative
    return _make_amount(negative, digits)


def parse_debit_credit(debit_text: str, credit_text: str, profile: Profile) -> Amount:
    """Separate debit and credit columns, normalised so money in is positive.

    Rows that cannot be read one way only are errors: both columns filled, both
    blank, or a negative number in either column.
    """
    cells = {}
    for label, column, text in (
        ("debit", profile.debit_column, debit_text),
        ("credit", profile.credit_column, credit_text),
    ):
        if text.strip() == "":
            continue
        negative, digits = _parse_number(text, profile)
        if negative:
            raise NormalizationError(
                f"negative value {text!r} in the {column} column is ambiguous; "
                "debit and credit columns must hold positive numbers"
            )
        cells[label] = digits
    if not cells:
        raise NormalizationError(
            f"both {profile.debit_column} and {profile.credit_column} are blank; "
            "no amount found"
        )
    nonzero = {k: v for k, v in cells.items() if Decimal(v) != 0}
    if len(nonzero) == 2:
        raise NormalizationError(
            f"both {profile.debit_column} ({debit_text.strip()}) and "
            f"{profile.credit_column} ({credit_text.strip()}) contain amounts; "
            "cannot tell which applies"
        )
    if not nonzero:
        return _make_amount(False, next(iter(cells.values())))
    (side, digits), = nonzero.items()
    money_out = (side == "debit") == (profile.debit_means == "money-out")
    return _make_amount(money_out, digits)
