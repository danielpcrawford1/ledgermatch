import unittest
from datetime import date
from decimal import Decimal

from helpers import HEADER, TempDirCase
from ledgermatch.loader import InputFileError, load_transactions


class FileLevelErrors(TempDirCase):
    def test_missing_file(self):
        with self.assertRaisesRegex(InputFileError, "not found"):
            load_transactions(self.tmp / "nope.csv")

    def test_folder_instead_of_file(self):
        with self.assertRaisesRegex(InputFileError, "folder"):
            load_transactions(self.tmp)

    def test_completely_empty_file(self):
        with self.assertRaisesRegex(InputFileError, "empty"):
            load_transactions(self.write("e.csv", ""))

    def test_missing_required_column(self):
        with self.assertRaisesRegex(InputFileError, "missing required column.*amount"):
            load_transactions(self.write("m.csv", "date,description\n"))

    def test_extra_columns_are_refused_not_ignored(self):
        with self.assertRaisesRegex(InputFileError, "unexpected column.*memo"):
            load_transactions(self.write("x.csv", "date,description,amount,memo\n"))

    def test_duplicate_header_names(self):
        with self.assertRaisesRegex(InputFileError, "duplicate column"):
            load_transactions(self.write("d.csv", "date,date,description,amount\n"))

    def test_binary_file(self):
        path = self.tmp / "b.csv"
        path.write_bytes(b"\xff\xfe\x00\x80\x81binary")
        with self.assertRaises(InputFileError):
            load_transactions(path)

    def test_unterminated_quote(self):
        path = self.write("q.csv", HEADER + '2026-01-01,"unclosed,1.00\n')
        with self.assertRaises(InputFileError):
            load_transactions(path)


class ValidFiles(TempDirCase):
    def test_header_only_is_valid_and_empty(self):
        result = load_transactions(self.write("h.csv", HEADER))
        self.assertEqual((result.transactions, result.problems), ([], []))

    def test_basic_row_and_raw_text_preserved(self):
        result = load_transactions(self.write("a.csv", HEADER + "2026-02-03,Rent,-1800.50 \n"))
        t = result.transactions[0]
        self.assertEqual((t.date, t.amount, t.line), (date(2026, 2, 3), Decimal("-1800.50"), 2))
        self.assertEqual((t.raw_date, t.raw_amount), ("2026-02-03", "-1800.50"))

    def test_trailing_zeros_kept_in_raw_text(self):
        t = load_transactions(self.write("z.csv", HEADER + "2026-01-01,a,10.10\n")).transactions[0]
        self.assertEqual(t.raw_amount, "10.10")

    def test_column_order_and_case_do_not_matter(self):
        result = load_transactions(self.write("o.csv", "Amount,DATE,Description\n1.50,2026-02-03,x\n"))
        self.assertEqual(result.transactions[0].amount, Decimal("1.50"))

    def test_description_kept_exactly(self):
        t = load_transactions(self.write("s.csv", HEADER + '2026-01-01,"  Smith, John  ",5\n')).transactions[0]
        self.assertEqual(t.description, "  Smith, John  ")

    def test_excel_bom_is_handled(self):
        path = self.write("bom.csv", "﻿" + HEADER + "2026-01-01,a,1\n")
        self.assertEqual(len(load_transactions(path).transactions), 1)

    def test_windows_line_endings(self):
        path = self.write("crlf.csv", "date,description,amount\r\n2026-01-01,a,1\r\n2026-01-02,b,2\r\n")
        self.assertEqual(len(load_transactions(path).transactions), 2)

    def test_blank_lines_skipped_and_line_numbers_stay_true(self):
        result = load_transactions(self.write("bl.csv", HEADER + "\n2026-01-01,a,1\n\n2026-01-02,b,2\n"))
        self.assertEqual([t.line for t in result.transactions], [3, 5])

    def test_multiline_quoted_field_reports_starting_line(self):
        result = load_transactions(self.write("ml.csv", HEADER + '2026-01-01,"two\nlines",1\n2026-01-02,b,2\n'))
        self.assertEqual([t.line for t in result.transactions], [2, 4])


class RowProblems(TempDirCase):
    def problems(self, body):
        return load_transactions(self.write("p.csv", HEADER + body)).problems

    def test_invalid_dates(self):
        for bad in ("2026-13-01", "2026-02-30", "01/02/2026", "20260105", "2026-1-5",
                    "", "yesterday", "2026-W01-1"):
            with self.subTest(bad=bad):
                problems = self.problems(f"{bad},x,1.00\n")
                self.assertEqual(len(problems), 1)
                self.assertIn("invalid date", problems[0].message)
                self.assertEqual(problems[0].line, 2)

    def test_invalid_amounts(self):
        for bad in ("abc", "", '"1,000.00"', "NaN", "Infinity", "$5", "1e3", "(5.00)",
                    "5.", ".5", "--5", "+5", "1 000"):
            with self.subTest(bad=bad):
                problems = self.problems(f"2026-01-01,x,{bad}\n")
                self.assertEqual(len(problems), 1)
                self.assertIn("invalid amount", problems[0].message)

    def test_all_problems_reported_not_just_the_first(self):
        problems = self.problems("bad,x,1\n2026-01-01,ok,1\n2026-01-02,x,oops\n2026-01-03,short\n")
        self.assertEqual([p.line for p in problems], [2, 4, 5])

    def test_bad_row_does_not_hide_good_rows(self):
        result = load_transactions(self.write("m.csv", HEADER + "bad,x,1\n2026-01-01,ok,1\n"))
        self.assertEqual((len(result.transactions), len(result.problems)), (1, 1))

    def test_row_with_two_problems_reports_both(self):
        self.assertEqual(len(self.problems("nope,x,nope\n")), 2)

    def test_wrong_column_count(self):
        problems = self.problems("2026-01-01,only two\n2026-01-01,a,1,extra\n")
        self.assertEqual(len(problems), 2)
        self.assertIn("expected 3 columns but found 2", problems[0].message)


if __name__ == "__main__":
    unittest.main()
