import csv
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from helpers import HEADER, TempDirCase, txn
from ledgermatch.cli import main
from ledgermatch.engine import reconcile
from ledgermatch.report import OutputExistsError, format_summary, write_reports

SAMPLES = Path(__file__).resolve().parent.parent / "sample_data"


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class ReportTests(TempDirCase):
    def test_reports_keep_original_text_and_flag_review_rows(self):
        bank = [txn("2026-01-01", "10.10", "b", line=2), txn("2026-01-01", "10.10", "b", line=3)]
        register = [txn("2026-01-01", "10.1", "r", line=2)]
        result = reconcile(bank, register)
        write_reports(result, self.tmp / "out")
        matched = read_csv(self.tmp / "out" / "matched.csv")
        bank_only = read_csv(self.tmp / "out" / "bank_only.csv")
        self.assertEqual(matched[0]["amount"], "10.10")  # raw text, not normalised
        self.assertIn("review", matched[0]["review"])
        self.assertIn("bank has 2, register has 1", bank_only[0]["review"])
        self.assertEqual(read_csv(self.tmp / "out" / "register_only.csv"), [])

    def test_refuses_to_overwrite_without_force(self):
        result = reconcile([], [])
        write_reports(result, self.tmp)
        with self.assertRaises(OutputExistsError):
            write_reports(result, self.tmp)
        write_reports(result, self.tmp, force=True)  # allowed

    def test_nothing_written_when_any_file_would_be_overwritten(self):
        (self.tmp / "bank_only.csv").write_text("precious", encoding="utf-8")
        with self.assertRaises(OutputExistsError):
            write_reports(reconcile([], []), self.tmp)
        self.assertFalse((self.tmp / "matched.csv").exists())
        self.assertEqual((self.tmp / "bank_only.csv").read_text(encoding="utf-8"), "precious")

    def test_summary_control_totals(self):
        bank = [txn("2026-01-01", "100.00"), txn("2026-01-02", "-5.25")]
        register = [txn("2026-01-01", "100.00"), txn("2026-01-03", "7.00")]
        text = format_summary(reconcile(bank, register))
        self.assertIn("Bank file:      2 rows, total 94.75", text)
        self.assertIn("Register file:  2 rows, total 107.00", text)
        self.assertIn("Only in bank:       1 rows, total -5.25", text)


class CliTests(TempDirCase):
    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def test_sample_data_end_to_end(self):
        code, out, _ = self.run_cli(SAMPLES / "bank.csv", SAMPLES / "register.csv",
                                    "-o", self.tmp / "o")
        self.assertEqual(code, 0)
        self.assertIn("Matched:            6 pairs", out)
        self.assertIn("2026-03-04  -4.50  bank 2 / register 1", out)
        self.assertEqual(len(read_csv(self.tmp / "o" / "bank_only.csv")), 2)
        self.assertEqual(len(read_csv(self.tmp / "o" / "register_only.csv")), 1)

    def test_invalid_rows_in_both_files_are_all_reported_and_nothing_reconciled(self):
        b = self.write("b.csv", HEADER + "bad,a,1\n")
        r = self.write("r.csv", HEADER + "2026-01-01,a,oops\n")
        code, out, err = self.run_cli(b, r, "-o", self.tmp / "o")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("2 invalid row(s)", err)
        self.assertIn("invalid date", err)
        self.assertIn("invalid amount", err)
        self.assertFalse((self.tmp / "o").exists())

    def test_file_error_gives_message_not_traceback(self):
        code, _, err = self.run_cli(self.tmp / "missing.csv", self.tmp / "also.csv")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("Error:"))

    def test_second_run_refuses_to_overwrite(self):
        b = self.write("b.csv", HEADER + "2026-01-01,a,1\n")
        args = (b, b, "-o", self.tmp / "o")
        self.assertEqual(self.run_cli(*args)[0], 0)
        code, _, err = self.run_cli(*args)
        self.assertEqual(code, 1)
        self.assertIn("--force", err)
        self.assertEqual(self.run_cli(*args, "--force")[0], 0)


if __name__ == "__main__":
    unittest.main()
