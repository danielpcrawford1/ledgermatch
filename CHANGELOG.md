# Changelog

## 0.2.0

Configurable import profiles, so real bank and accounting exports can be used
without converting them first. The matching engine is unchanged.

- Profiles (TOML files) map any CSV layout to LedgerMatch's transactions:
  column names, several description columns, date format, delimiter, encoding,
  title lines above the header, thousands/decimal separators, currency symbol,
  bracketed negatives.
- A single signed amount column, or separate Debit and Credit columns. The
  meaning of "debit" must be stated explicitly in the profile.
- Bank and register files can use different profiles in one run
  (`--bank-profile`, `--register-profile`).
- `--validate-only` prints counts, date range and money-in/out totals for each
  file so a profile can be checked against the statement before reconciling.
- Reports now include an `original` column (bank/register original for matches)
  holding the complete source row as JSON, and print dates as YYYY-MM-DD.
- Strict validation: unknown profile settings, two-digit years, ambiguous
  debit/credit rows and malformed numbers are errors, never guesses.
- The default `standard` profile behaves exactly as in 0.1.
- Internal: `Transaction.raw_amount` renamed `amount_text`; new `original` field.

## 0.1.0

First release: the reconciliation engine and a command-line interface.

- Match bank and register CSVs on exact date and exact amount, one-to-one.
- Duplicates handled; repeated date-and-amount groups are flagged for review.
- Strict input validation; every invalid row is reported together.
- Reports: `matched.csv`, `bank_only.csv`, `register_only.csv`, plus a terminal
  summary with control totals.
- Exact `Decimal` arithmetic. Works fully offline, standard library only.
