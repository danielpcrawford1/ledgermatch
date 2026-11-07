# Import profiles

A profile tells LedgerMatch how to read one particular CSV layout. You choose one per file:

```bash
ledgermatch bank.csv register.csv \
  --bank-profile profiles/my-bank.toml \
  --register-profile profiles/my-books.toml
```

The value is either the built-in name `standard` (the original `date,description,amount` layout, the default) or the path to a `.toml` file. The two files can use different profiles.

**Always validate a new profile first:**

```bash
ledgermatch bank.csv register.csv --bank-profile my-bank.toml --register-profile my-books.toml --validate-only
```

It prints, for each file, the number of transactions, the date range, and the money-in, money-out and net totals. Compare them with the bank statement and your ledger. If the net does not equal the statement's change in balance, something is being read wrongly: fix the profile before reconciling.

## Example: signed amount column

```toml
name = "credit-union-signed"

[file]
skip_rows = 2                  # title lines before the header row

[columns]
date = "Posting Date"
description = ["Payee", "Memo"]
amount = "Amount"

[dates]
format = "%m/%d/%Y"

[amounts]
thousands_separator = ","
```

## Example: debit and credit columns

```toml
name = "ledger-debit-credit"

[columns]
date = "Date"
description = ["Name", "Memo"]
debit = "Debit"
credit = "Credit"

[dates]
format = "%d-%b-%Y"

[amounts]
debit_means = "money-in"       # required; see below
thousands_separator = ","
```

Both are in `sample_data/profiles/`, with matching fictional exports in `sample_data/`.

## All settings

Every setting is optional unless marked required. Misspelt or unknown settings are errors.

| section | setting | meaning | default |
| --- | --- | --- | --- |
| top | `name` | label shown in the summary | file name |
| top | `description` | free text for you | empty |
| `[file]` | `encoding` | text encoding; try `cp1252` for older Windows exports | `utf-8-sig` |
| | `delimiter` | one character, e.g. `";"` or `"\t"` | `,` |
| | `skip_rows` | lines above the header row | `0` |
| | `extra_columns` | `preserve` keeps unused columns in the reports; `error` refuses them | `preserve` |
| `[columns]` | `date` | **required.** Header name of the date column | |
| | `description` | one header name or a list; several are joined with ` - ` | none |
| | `amount` | one signed amount column, **or** | |
| | `debit` and `credit` | two columns (use these instead of `amount`) | |
| `[dates]` | `format` | a Python date format; must include `%Y`, a month and `%d` | `%Y-%m-%d` |
| | `zero_padded` | `false` accepts `3/4/2026` for `%m/%d/%Y` | `true` |
| `[amounts]` | `amount_sign` | single column only: `inverted` flips every sign | `as-is` |
| | `debit_means` | **required with debit/credit:** `money-out` or `money-in` | |
| | `thousands_separator` | `","`, `"."`, `" "` or `"'"` | none |
| | `decimal_separator` | `"."` or `","` | `.` |
| | `currency_symbol` | e.g. `"$"` | none |
| | `parentheses_negative` | read `(5.00)` as -5.00 | `false` |

Header names are matched ignoring capitalisation and surrounding spaces.

### Date formats

Write the format exactly as the file writes dates: `%m/%d/%Y` for 03/04/2026, `%d-%b-%Y` for 04-Mar-2026. Month-first and day-first are the same text for many dates, so LedgerMatch never guesses; **choose the format deliberately and check the date range from `--validate-only`**. Two-digit years (`%y`) are refused. A time after the date is allowed (`%Y-%m-%d %H:%M`); only the date is used for matching.

## How debits and credits are read

Everything is normalised to one convention: **money in is positive, money out is negative.**

A bank calls a withdrawal a "debit". In your books, a debit to the cash account is a deposit. The same word means opposite things, so a profile with debit and credit columns must say which: `debit_means = "money-out"` (bank view) or `"money-in"` (a cash account in your ledger). There is no default on purpose. Getting it backwards makes nothing match, and the summary will show it.

Rows LedgerMatch will not read, each reported with its line number:

- both Debit and Credit contain amounts (one may be `0`);
- both are blank;
- a negative or bracketed number in either column;
- anything that is not a valid number for the profile.

## What is preserved

- Every row keeps **all** of its original columns, including ones LedgerMatch does not use (running balance, check number, reference). Reports hold them as JSON in the `original` columns.
- Amounts keep the digits from the file: `10.10` stays `10.10`, and a credit of `10.10` becomes `-10.10`. Only the sign and separators change.
- Description columns are joined only for display; the originals remain in `original`.
- Reports print dates as `YYYY-MM-DD` whichever format the input used. The date as written is in `original`.

## What is refused instead of guessed

Text that does not match the profile exactly is an error: amounts like `5.00-`, `5.00 CR`, `1e3`, `NaN`; thousands groups in the wrong place (`1,23`); dates with the wrong order, impossible days, or missing leading zeros (unless `zero_padded = false`). If any row is invalid, LedgerMatch lists every bad row and reconciles nothing.

## Not supported (yet)

- A separate "type" column (`DR`/`CR`) with unsigned amounts.
- Footer or total rows at the end of a file: remove them, or they are reported as invalid rows.
- Per-row currencies, and files split across several CSVs.
