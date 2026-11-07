import csv
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from helpers import TempDirCase
from ledgermatch.cli import main

DATA = Path(__file__).resolve().parent.parent / "sample_data"
BANK = DATA / "bank_export_credit_union.csv"
REGISTER = DATA / "register_export_ledger.csv"
BANK_PROFILE = DATA / "profiles" / "credit-union-signed.toml"
REGISTER_PROFILE = DATA / "profiles" / "ledger-debit-credit.toml"


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main([str(a) for a in args])
    return code, out.getvalue(), err.getvalue()


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class MixedProfiles(TempDirCase):
    def reconcile(self, out, *extra):
        return run(BANK, REGISTER, "--bank-profile", BANK_PROFILE,
                   "--register-profile", REGISTER_PROFILE, "-o", out, *extra)

    def test_different_profiles_in_one_run_match_the_standard_sample(self):
        code, out, _ = self.reconcile(self.tmp / "mixed")
        self.assertEqual(code, 0)
        std_code, std_out, _ = run(DATA / "bank.csv", DATA / "register.csv", "-o", self.tmp / "std")
        self.assertEqual(std_code, 0)
        for name in ("matched.csv", "bank_only.csv", "register_only.csv"):
            mixed = [(r["date"], r.get("amount") or r["amount"]) for r in read_csv(self.tmp / "mixed" / name)]
            std = [(r["date"], r["amount"]) for r in read_csv(self.tmp / "std" / name)]
            self.assertEqual(mixed, std, name)
        # Same totals and the same duplicate warning as the standard-format sample.
        for text in ("Matched:            6 pairs, total 12983.13",
                     "Only in bank:       2 rows, total -19.50",
                     "Only in register:   1 rows, total -340.00",
                     "2026-03-04  -4.50  bank 2 / register 1"):
            self.assertIn(text, out)
            self.assertIn(text, std_out)

    def test_summary_names_the_profiles_used(self):
        _, out, _ = self.reconcile(self.tmp / "o")
        self.assertIn("(profile: credit-union-signed)", out)
        self.assertIn("(profile: ledger-debit-credit)", out)

    def test_reports_carry_the_original_rows(self):
        self.reconcile(self.tmp / "o")
        row = read_csv(self.tmp / "o" / "bank_only.csv")[0]
        original = json.loads(row["original"])
        self.assertEqual(original["Running Balance"], "10,691.00")  # an unused column survives
        self.assertEqual(original["Posting Date"], "03/04/2026")    # raw date text survives
        self.assertEqual(row["date"], "2026-03-04")
        reg_only = read_csv(self.tmp / "o" / "register_only.csv")[0]
        self.assertEqual(json.loads(reg_only["original"])["Credit"], "340.00")
        self.assertEqual(reg_only["amount"], "-340.00")  # a credit in a cash account = money out
        matched = read_csv(self.tmp / "o" / "matched.csv")[0]
        self.assertEqual(json.loads(matched["register_original"])["Num"], "JE-1")

    def test_every_input_row_appears_in_exactly_one_report(self):
        self.reconcile(self.tmp / "o")
        bank_lines = {int(r["bank_line"]) for r in read_csv(self.tmp / "o" / "matched.csv")}
        bank_lines |= {int(r["line"]) for r in read_csv(self.tmp / "o" / "bank_only.csv")}
        self.assertEqual(bank_lines, set(range(4, 12)))   # data rows are file lines 4-11
        reg_lines = {int(r["register_line"]) for r in read_csv(self.tmp / "o" / "matched.csv")}
        reg_lines |= {int(r["line"]) for r in read_csv(self.tmp / "o" / "register_only.csv")}
        self.assertEqual(reg_lines, set(range(2, 9)))

    def test_wrong_direction_for_debits_changes_the_answer_loudly(self):
        # If the register's debit meaning were wrong, nothing would match: the
        # control totals and the unmatched list expose it.
        wrong = self.tmp / "wrong.toml"
        wrong.write_text(REGISTER_PROFILE.read_text().replace("money-in", "money-out"))
        code, out, _ = run(BANK, REGISTER, "--bank-profile", BANK_PROFILE,
                           "--register-profile", wrong, "-o", self.tmp / "o")
        self.assertEqual(code, 0)
        self.assertIn("Matched:            0 pairs", out)

    def test_standard_profile_on_a_real_export_fails_clearly(self):
        code, _, err = run(BANK, REGISTER, "-o", self.tmp / "o")
        self.assertEqual(code, 1)
        self.assertIn("missing required column", err)
        self.assertFalse((self.tmp / "o").exists())


class ValidateOnly(TempDirCase):
    def test_prints_control_figures_and_writes_nothing(self):
        code, out, _ = run(BANK, REGISTER, "--bank-profile", BANK_PROFILE,
                           "--register-profile", REGISTER_PROFILE,
                           "--validate-only", "-o", self.tmp / "o")
        self.assertEqual(code, 0)
        self.assertIn("Bank file (profile: credit-union-signed): 8 transactions", out)
        self.assertIn("dates 2026-03-01 to 2026-03-09", out)
        self.assertIn("net       12963.63", out)  # equals the file's own final running balance
        self.assertIn("net       12643.13", out)
        self.assertFalse((self.tmp / "o").exists())

    def test_still_reports_invalid_rows(self):
        bad = self.write("bad.csv", BANK.read_text().replace("03/05/2026", "05/03/26"))
        code, _, err = run(bad, REGISTER, "--bank-profile", BANK_PROFILE,
                           "--register-profile", REGISTER_PROFILE, "--validate-only")
        self.assertEqual(code, 1)
        self.assertIn("invalid date '05/03/26'", err)
        self.assertIn("line 9", err)


class ProfileErrors(TempDirCase):
    def test_unknown_profile(self):
        code, _, err = run(DATA / "bank.csv", DATA / "register.csv", "--bank-profile", "nope")
        self.assertEqual((code, err.startswith("Error: profile 'nope' not found")), (1, True))

    def test_invalid_profile_file(self):
        bad = self.write("bad.toml", '[columns]\ndate="D"\n')
        code, _, err = run(DATA / "bank.csv", DATA / "register.csv", "--register-profile", bad)
        self.assertEqual(code, 1)
        self.assertIn("either amount, or both debit and credit", err)


if __name__ == "__main__":
    unittest.main()
