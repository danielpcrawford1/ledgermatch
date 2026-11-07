"""Command-line interface. Parses arguments, calls the engine, prints results."""

import argparse
import sys

from ledgermatch import __version__
from ledgermatch.engine import reconcile
from ledgermatch.loader import InputFileError, RowProblem, load_transactions
from ledgermatch.profiles import ProfileError, load_profile
from ledgermatch.report import (
    OutputExistsError,
    format_summary,
    format_validation,
    write_reports,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ledgermatch",
        description="Reconcile a bank CSV against an accounting register CSV. "
        "Transactions match on exact date and exact amount.",
    )
    parser.add_argument("bank", help="bank transactions CSV (date,description,amount)")
    parser.add_argument("register", help="register transactions CSV (same columns)")
    parser.add_argument(
        "--bank-profile", default="standard", metavar="PROFILE",
        help="import profile for the bank file: 'standard' or a .toml file (default: standard)",
    )
    parser.add_argument(
        "--register-profile", default="standard", metavar="PROFILE",
        help="import profile for the register file (default: standard)",
    )
    parser.add_argument(
        "--validate-only", action="store_true",
        help="read both files and print counts and totals; do not reconcile or write reports",
    )
    parser.add_argument(
        "-o", "--output-dir", default="ledgermatch-output",
        help="folder for the report CSV files (default: ledgermatch-output)",
    )
    parser.add_argument(
        "--force", action="store_true", help="overwrite existing report files"
    )
    parser.add_argument("--version", action="version", version=f"ledgermatch {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Return 0 on success, 1 if the inputs or profiles are unusable or output would be overwritten."""
    args = build_parser().parse_args(argv)

    problems: list[RowProblem] = []
    loaded = []
    profiles = []
    try:
        for label, path, spec in (
            ("Bank file", args.bank, args.bank_profile),
            ("Register file", args.register, args.register_profile),
        ):
            profile = load_profile(spec)
            result = load_transactions(path, profile)
            profiles.append(profile)
            loaded.append(result.transactions)
            problems.extend(result.problems)
    except (InputFileError, ProfileError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if problems:
        print(f"Error: {len(problems)} invalid row(s) found. Nothing was reconciled; "
              "fix these rows (or the profile) and run again:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    if args.validate_only:
        for label, profile, transactions in zip(("Bank file", "Register file"), profiles, loaded):
            print(format_validation(label, profile.name, transactions))
        return 0

    result = reconcile(*loaded)
    try:
        paths = write_reports(result, args.output_dir, force=args.force)
    except OutputExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(format_summary(result, profiles[0].name, profiles[1].name))
    print()
    for path in paths:
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
