import unittest
from dataclasses import replace
from decimal import Decimal

from helpers import TempDirCase
from ledgermatch.loader import InputFileError, load_transactions
from ledgermatch.profiles import STANDARD

BANK = replace(
    STANDARD, name="bank", extra_columns="preserve", date_column="Posting Date",
    description_columns=("Payee", "Memo"), amount_column="Amount", date_format="%m/%d/%Y",
    thousands_separator=",", skip_rows=2,
)
LEDGER = replace(
    STANDARD, name="ledger", extra_columns="preserve", date_column="Date",
    description_columns=("Name", "Memo"), amount_column=None, debit_column="Debit",
    credit_column="Credit", debit_means="money-in", date_format="%d-%b-%Y",
)


class SignedAmountProfile(TempDirCase):
    CSV = ("Title line\nSecond title line\n"
           "Posting Date,Payee,Memo,Amount,Balance\n"
           '03/01/2026,A Co, Deposit ,"1,000.00","1,000.00"\n'
           "03/02/2026,B Co,Rent,-250.50,749.50\n")

    def test_reads_profile_layout(self):
        result = load_transactions(self.write("b.csv", self.CSV), BANK)
        self.assertEqual(result.problems, [])
        first, second = result.transactions
        self.assertEqual((first.amount, first.amount_text), (Decimal("1000.00"), "1000.00"))
        self.assertEqual(second.amount, Decimal("-250.50"))
        self.assertEqual(first.description, "A Co - Deposit")

    def test_line_numbers_count_the_skipped_title_lines(self):
        result = load_transactions(self.write("b.csv", self.CSV), BANK)
        self.assertEqual([t.line for t in result.transactions], [4, 5])

    def test_problem_line_numbers_also_count_skipped_lines(self):
        text = self.CSV + "13/45/2026,C,x,5,1\n"
        result = load_transactions(self.write("b.csv", text), BANK)
        self.assertEqual([p.line for p in result.problems], [6])

    def test_unused_columns_are_preserved_untouched(self):
        t = load_transactions(self.write("b.csv", self.CSV), BANK).transactions[0]
        self.assertEqual(dict(t.original), {
            "Posting Date": "03/01/2026", "Payee": "A Co", "Memo": " Deposit ",
            "Amount": "1,000.00", "Balance": "1,000.00",
        })

    def test_every_original_cell_is_kept_in_order(self):
        t = load_transactions(self.write("b.csv", self.CSV), BANK).transactions[1]
        self.assertEqual([k for k, _ in t.original],
                         ["Posting Date", "Payee", "Memo", "Amount", "Balance"])
        self.assertEqual([v for _, v in t.original], ["03/02/2026", "B Co", "Rent", "-250.50", "749.50"])

    def test_standard_profile_still_refuses_extra_columns(self):
        with self.assertRaisesRegex(InputFileError, "unexpected column.*memo"):
            load_transactions(self.write("x.csv", "date,description,amount,memo\n"))

    def test_missing_mapped_column_names_what_was_found(self):
        path = self.write("m.csv", "Title\nTitle2\nPosting Date,Payee,Amt\n")
        with self.assertRaisesRegex(InputFileError, r"Memo, Amount.*Header found: Posting Date, Payee, Amt"):
            load_transactions(path, BANK)

    def test_skip_rows_beyond_file_end_is_an_empty_file_error(self):
        with self.assertRaisesRegex(InputFileError, "empty"):
            load_transactions(self.write("s.csv", "only one line\n"), BANK)

    def test_header_matching_ignores_case_and_spaces(self):
        text = "T\nT\n posting date ,PAYEE,memo,AMOUNT,x\n03/01/2026,a,b,5,0\n"
        self.assertEqual(len(load_transactions(self.write("c.csv", text), BANK).transactions), 1)


class DebitCreditProfile(TempDirCase):
    CSV = ("Date,Num,Name,Memo,Debit,Credit\n"
           '01-Mar-2026,1,Owner,Funding,"10,000.00",\n'
           "03-Mar-2026,2,Landlord,Rent,,1800.00\n")
    LEDGER = replace(LEDGER, thousands_separator=",")

    def test_debit_is_money_in_credit_is_money_out(self):
        result = load_transactions(self.write("l.csv", self.CSV), self.LEDGER)
        self.assertEqual([t.amount for t in result.transactions], [Decimal("10000.00"), Decimal("-1800.00")])
        self.assertEqual([t.amount_text for t in result.transactions], ["10000.00", "-1800.00"])

    def test_original_keeps_both_debit_and_credit_cells(self):
        t = load_transactions(self.write("l.csv", self.CSV), self.LEDGER).transactions[1]
        self.assertEqual(dict(t.original)["Debit"], "")
        self.assertEqual(dict(t.original)["Credit"], "1800.00")

    def test_ambiguous_rows_are_reported_with_lines_not_guessed(self):
        text = ("Date,Num,Name,Memo,Debit,Credit\n"
                "01-Mar-2026,1,A,x,5.00,5.00\n"
                "02-Mar-2026,2,B,y,,\n"
                "03-Mar-2026,3,C,z,-5.00,\n"
                "04-Mar-2026,4,D,w,7.00,\n")
        result = load_transactions(self.write("l.csv", text), self.LEDGER)
        self.assertEqual([p.line for p in result.problems], [2, 3, 4])
        self.assertEqual(len(result.transactions), 1)

    def test_invalid_date_with_ambiguous_amount_gives_both_messages(self):
        text = "Date,Num,Name,Memo,Debit,Credit\nnope,1,A,x,5,5\n"
        problems = load_transactions(self.write("l.csv", text), self.LEDGER).problems
        self.assertEqual(len(problems), 2)


class FileFormatOptions(TempDirCase):
    def test_semicolon_delimiter_and_decimal_comma(self):
        profile = replace(STANDARD, delimiter=";", decimal_separator=",", thousands_separator=".",
                          extra_columns="preserve")
        text = "date;description;amount\n2026-03-01;Müller & Co;-1.234,56\n"
        t = load_transactions(self.write("e.csv", text), profile).transactions[0]
        self.assertEqual((t.amount, t.description), (Decimal("-1234.56"), "Müller & Co"))

    def test_non_utf8_encoding(self):
        profile = replace(STANDARD, encoding="cp1252")
        path = self.tmp / "w.csv"
        path.write_bytes("date,description,amount\n2026-03-01,Café,5\n".encode("cp1252"))
        self.assertEqual(load_transactions(path, profile).transactions[0].description, "Café")
        with self.assertRaisesRegex(InputFileError, "not readable as utf-8-sig"):
            load_transactions(path)  # the standard profile expects UTF-8

    def test_blank_and_repeated_headers_still_get_unique_original_keys(self):
        profile = replace(STANDARD, extra_columns="preserve")
        text = "date,description,amount,,Note,Note,\n2026-03-01,a,5,x,n1,n2,\n"
        t = load_transactions(self.write("h.csv", text), profile).transactions[0]
        self.assertEqual(len(dict(t.original)), 7)
        self.assertEqual(dict(t.original)["Note (column 6)"], "n2")

    def test_repeated_mapped_column_is_an_error(self):
        with self.assertRaisesRegex(InputFileError, "duplicate column"):
            load_transactions(self.write("d.csv", "date,date,description,amount\n"))


if __name__ == "__main__":
    unittest.main()
