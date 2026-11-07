# LedgerMatch

Offline CSV reconciliation for bookkeepers and small businesses. Give it a bank export and an accounting-register export; it tells you what matches, what is only in the bank, and what is only in your books.

Version 0.1 is deliberately small. Correctness of the numbers comes first.

## Principles

- **Nothing is silently dropped or changed.** Every input row ends up in exactly one report, and dates and amounts are printed exactly as you supplied them.
- **Exact money.** Amounts use exact decimal arithmetic, never floating point.
- **Descriptions are never used for matching.** "Rent" vs "Rent March" proves nothing; only date and amount count.
- **Duplicates are flagged.** If the same date and amount appears more than once, the tool says so and asks you to review.
- **Bad input stops the run.** Every invalid row is listed at once, and nothing is reconciled until the file is fixed.
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
| `--force` | overwrite existing reports (otherwise the run refuses) |
| `--version` | print the version |

Exit code `0` means the run completed (even if some rows are unmatched, since that is a normal result). Exit code `1` means the input was unusable or reports would have been overwritten.

## Input format

CSV with a header row and exactly these columns, in any order and any capitalisation:

| column | rule |
| --- | --- |
| `date` | `YYYY-MM-DD` |
| `description` | any text (quote it if it contains a comma) |
| `amount` | plain number; negative for money out, e.g. `-86.40` |

Not accepted, and reported as errors: currency symbols, thousands separators (`1,000.00`), brackets for negatives (`(5.00)`), exponents (`1e3`), other date formats, and extra columns. LedgerMatch refuses them rather than guessing.

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
date,description,amount,line,review
2026-03-04,Coffee,-4.50,5,"review: bank has 2, register has 1 with this date and amount"
2026-03-05,Bank service fee,-15.00,6,
```

`line` is the row's line number in your original file.

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

## Current limitations (version 0.1)

- Exact date and exact amount only; no tolerance for a bank posting a day late.
- Two files, one currency, fixed column names and date format.
- Whole files are read into memory.
- Matching one-to-one only; one bank deposit covering several invoices will not match.
- Reports are CSV only.

## Architecture and contributing

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the code is organised and how to extend it safely. Changes are listed in [CHANGELOG.md](CHANGELOG.md).

## License

MIT. See [LICENSE](LICENSE).
