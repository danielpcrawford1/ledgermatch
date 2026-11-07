# Architecture

LedgerMatch is a small pipeline: **load → reconcile → report**, where loading is configured by an import profile. Each stage lives in its own module and talks to the others only through the data types in `models.py`.

```
 profile (.toml) ──> profiles.py ─┐
                                  ├─> loader.py ──> [Transaction, ...] ──> engine.py ──> ReconciliationResult ──> report.py ──> CSV files + summary
 CSV files ───────> normalize.py ─┘                                                                                  ▲
                                                               cli.py wires the stages together ──────────────────────┘
```

Everything left of `[Transaction, ...]` is the **import side**; it can change freely for new bank formats. The engine only ever sees `Transaction`s and never learns which profile produced them.

| module | job | may import |
| --- | --- | --- |
| `models.py` | data types only (`Transaction`, `Match`, `AmbiguousGroup`, `ReconciliationResult`) | nothing from the package |
| `engine.py` | the matching rules; pure logic, no files, no printing | `models` |
| `profiles.py` | import settings: the `Profile` type, TOML loading and strict validation of it | nothing from the package |
| `normalize.py` | pure functions: date text → date, amount text / debit-credit → exact `Decimal` | `profiles` |
| `loader.py` | read CSV with a profile into `Transaction`s; report bad rows | `models`, `profiles`, `normalize` |
| `report.py` | format the result as a summary and CSV files | `models` |
| `cli.py` | arguments, calling the stages, exit codes | everything |

`tests/test_architecture.py` enforces these boundaries, so a future change that makes the engine depend on files or the command line fails the tests.

## Design decisions

- **The engine never sees raw text.** The import side turns text into dates and `Decimal`s, so the engine only compares exact values.
- **Original data is carried along.** `Transaction.original` holds every column of the source row, and `amount_text` keeps the file's own digits. Normalising (dates, signs, separators) therefore never destroys information; reports include it as JSON.
- **Profiles are configuration, not code.** A new bank layout is a new `.toml` file. Only a genuinely new kind of rule (for example a `DR`/`CR` type column) needs a change in `normalize.py` and `profiles.py`, and never in `engine.py`.
- **Ambiguity is refused.** Things that cannot be read one way only (both debit and credit filled, a negative debit, unknown settings, two-digit years) are errors. The meaning of "debit" is a required setting, not a default.
- **Validation is strict and total.** The loader reports every bad row, and the CLI refuses to reconcile if any row is bad. A row is never skipped to "make it work".
- **Ambiguity is data, not a guess.** Repeated date-and-amount groups are returned in `ReconciliationResult.ambiguous_groups`; the pairing within them is deterministic (file order) but flagged.
- **Invariant:** every input row appears exactly once in `matches`, `bank_only` or `register_only`. A randomised test checks this on hundreds of generated inputs.

## Adding a new bank format

1. Write a profile (see [PROFILES.md](PROFILES.md)) and run `--validate-only` against a real export; compare the totals to the statement.
2. If the profile cannot express something, extend `profiles.py` (a validated setting) and `normalize.py` (the parsing rule), add tests for both the accepted and the rejected cases, and leave `engine.py` alone.

## Adding a feature safely

1. Put new matching rules in `engine.py` (or a new module that imports only `models`). Never add file or print code there.
2. If you need new fields, add them to `models.py`, and have `loader.py` fill them.
3. New output formats go in `report.py` or a new module that reads a `ReconciliationResult`.
4. Write the test first, including a case where data must not be lost. Run the suite; the invariant test should keep passing.
5. Update `CHANGELOG.md` and the README limitations list.

## Not implemented

Date tolerance, many-to-one matching, other file formats, and a graphical interface. The structure leaves room for them, but none are implemented.
