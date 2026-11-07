# Architecture

LedgerMatch is a small pipeline: **load → reconcile → report**. Each stage lives in its own module and talks to the others only through the data types in `models.py`.

```
 CSV files ──> loader.py ──> [Transaction, ...] ──> engine.py ──> ReconciliationResult ──> report.py ──> CSV files + summary
                                                                                                ▲
                                                          cli.py wires the stages together ─────┘
```

| module | job | may import |
| --- | --- | --- |
| `models.py` | data types only (`Transaction`, `Match`, `AmbiguousGroup`, `ReconciliationResult`) | nothing from the package |
| `engine.py` | the matching rules; pure logic, no files, no printing | `models` |
| `loader.py` | read and strictly validate CSV into `Transaction`s | `models` |
| `report.py` | format the result as a summary and CSV files | `models` |
| `cli.py` | arguments, calling the stages, exit codes | everything |

`tests/test_architecture.py` enforces these boundaries, so a future change that makes the engine depend on files or the command line fails the tests.

## Design decisions

- **The engine never sees raw text.** The loader turns text into dates and `Decimal`s, so the engine only compares exact values.
- **Raw text is carried along.** `Transaction.raw_date` and `raw_amount` hold what the file contained, and reports print those, so output never rewrites your data.
- **Validation is strict and total.** The loader reports every bad row, and the CLI refuses to reconcile if any row is bad. A row is never skipped to "make it work".
- **Ambiguity is data, not a guess.** Repeated date-and-amount groups are returned in `ReconciliationResult.ambiguous_groups`; the pairing within them is deterministic (file order) but flagged.
- **Invariant:** every input row appears exactly once in `matches`, `bank_only` or `register_only`. A randomised test checks this on hundreds of generated inputs.

## Adding a feature safely

1. Put new matching rules in `engine.py` (or a new module that imports only `models`). Never add file or print code there.
2. If you need new fields, add them to `models.py`, and have `loader.py` fill them.
3. New output formats go in `report.py` or a new module that reads a `ReconciliationResult`.
4. Write the test first, including a case where data must not be lost. Run the suite; the invariant test should keep passing.
5. Update `CHANGELOG.md` and the README limitations list.

## Not in version 0.1

Date tolerance, many-to-one matching, configurable columns, other file formats and a graphical interface. The structure leaves room for them, but none are implemented.
