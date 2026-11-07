# Changelog

## 0.1.0

First release: the reconciliation engine and a command-line interface.

- Match bank and register CSVs on exact date and exact amount, one-to-one.
- Duplicates handled; repeated date-and-amount groups are flagged for review.
- Strict input validation; every invalid row is reported together.
- Reports: `matched.csv`, `bank_only.csv`, `register_only.csv`, plus a terminal
  summary with control totals.
- Exact `Decimal` arithmetic. Works fully offline, standard library only.
