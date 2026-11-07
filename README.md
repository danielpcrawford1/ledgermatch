# LedgerMatch

Offline CSV reconciliation for bookkeepers and small businesses. Give it a bank export and an accounting-register export, in whatever layout they come in; it tells you what matches, what is only in the bank, and what is only in your books.

It is deliberately small. Correctness of the numbers comes first.

## Principles

- **Nothing is silently dropped or changed.** Every input row ends up in exactly one report, and dates and amounts are printed exactly as you supplied them.
- **Exact money.** Amounts use exact decimal arithmetic, never floating point.
- **Descriptions are never used for matching.** "Rent" vs "Rent March" proves nothing; only date and amount count.
- **Duplicates are flagged.** If the same date and amount appears more than once, the tool says so and asks you to review.
- **Bad input stops the run.** Every invalid row is listed at once, and nothing is reconciled until the file is fixed.
- **Real exports, no guessing.** Import profiles map different bank and ledger layouts, each file with its own profile, and anything ambiguous is an error rather than a guess.
- **Offline.** No network, no accounts, no databases, no dependencies.

## How matching works

A bank transaction and a register transaction match when their **date is identical** and their **amount is identical** (`10.10` equals `10.1`). Each transaction is used at most once.

When the same date and amount occurs several times, the first bank row pairs with the first register row, the second with the second, and so on. Leftovers are reported as unmatched. Because nothing distinguishes identical rows, any group where this pairing involved a choice is listed under **Needs review** in the summary and in the `review` column of the reports.

Example: the bank shows two 4.50 coffees on 4 March and the register shows one. You get one match, one "only in bank" row, and a review note saying the bank has 2 and the register has 1, so you can decide which one is the missing entry.

## Install and run

Requires Python 3.11 or newer.

```bash
git clone https://github.com/danielpcrawford1/ledgermatch.git
cd ledgermatch
pip install .
ledgermatch sample_data/bank.csv sample_data/register.csv
```

Without installing: `PYTHONPATH=src python3 -m ledgermatch sample_data/bank.csv sample_data/register.csv`

| option | meaning |
| --- | --- |
| `-o`, `--output-dir` | where reports go (default `ledgermatch-output`) |
| `--bank-profile`, `--register-profile` | import profile for each file: `standard` or a `.toml` path (default `standard`) |
| `--validate-only` | read both files, print counts and totals, write nothing |
| `--force` | overwrite existing reports (otherwise the run refuses) |
| `--version` | print the version |

Exit code `0` means the run completed (even if some rows are unmatched, since that is a normal result). Exit code `1` means the input was unusable or reports would have been overwritten.

## Input formats and import profiles

By default LedgerMatch reads the `standard` layout: a header row with exactly `date`, `description` and `amount` (any order or capitalisation), dates as `YYYY-MM-DD`, plain numbers with negative for money out.

Real exports rarely look like that, so each file can use an **import profile**: a small TOML file describing that layout (column names, date format, signed amount or separate Debit/Credit columns, title lines above the header, thousands separators, and so on). The bank and register can use different profiles in the same run:

```bash
ledgermatch bank_export_credit_union.csv register_export_ledger.csv \
  --bank-profile sample_data/profiles/credit-union-signed.toml \
  --register-profile sample_data/profiles/ledger-debit-credit.toml
```

Check a new profile before relying on it:

```bash
ledgermatch bank.csv register.csv --bank-profile my-bank.toml --register-profile my-books.toml --validate-only
```

This prints each file's transaction count, date range, and money in, money out and net totals, to compare with the statement. Two fictional exports in different layouts are in `sample_data/`. See [docs/PROFILES.md](docs/PROFILES.md) for every setting, how debits and credits are interpreted, and what is preserved.

Everything is normalised to **money in positive, money out negative**. For debit/credit columns the profile must say whether a debit means money in or out; LedgerMatch will not guess.

## Example output

Running it on the sample files:

```
LedgerMatch reconciliation summary
==================================
Bank file:      8 rows, total 12963.63
Register file:  7 rows, total 12643.13

Matched:            6 pairs, total 12983.13
Only in bank:       2 rows, total -19.50
Only in register:   1 rows, total -340.00

Needs review (same date and amount appears more than once):
  2026-03-04  -4.50  bank 2 / register 1
```

Control totals let you prove nothing was lost: matched (12983.13) plus bank-only (-19.50) equals the bank total (12963.63).

`bank_only.csv`:

```
date,description,amount,line,review,original
2026-03-04,Coffee,-4.50,6,"review: bank has 2, register has 1 with this date and amount","{""date"": ""2026-03-04"", ""description"": ""Coffee"", ""amount"": ""-4.50""}"
2026-03-05,Bank service fee,-15.00,7,,"{""date"": ""2026-03-05"", ""description"": ""Bank service fee"", ""amount"": ""-15.00""}"
```

`line` is the row's line number in your original file, and `original` holds the complete original row as JSON (including columns LedgerMatch does not use), so nothing from the input is lost. Reports always show dates as `YYYY-MM-DD`, whatever format the input used.

An invalid file looks like this:

```
Error: 2 invalid row(s) found. Nothing was reconciled; fix these rows and run again:
  bank.csv, line 3: invalid date '01/02/2026'; use YYYY-MM-DD, for example 2026-01-31
  bank.csv, line 7: invalid amount '$5'; use a plain number such as 12.50 or -3.00 ...
```

## Run the tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

All sample and test data is fictional.

## Current limitations

- Exact date and exact amount only; no tolerance for a bank posting a day late.
- Two files, one currency. No `DR`/`CR` type column and no footer rows (see [docs/PROFILES.md](docs/PROFILES.md)).
- Whole files are read into memory.
- Matching one-to-one only; one bank deposit covering several invoices will not match.
- Reports are CSV only.

## Architecture and contributing

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the code is organised and how to extend it safely. Changes are listed in [CHANGELOG.md](CHANGELOG.md).

## License

MIT. See [LICENSE](LICENSE).
