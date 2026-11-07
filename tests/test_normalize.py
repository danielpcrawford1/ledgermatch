import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal

from ledgermatch.normalize import (
    NormalizationError, parse_date, parse_debit_credit, parse_signed_amount,
)
from ledgermatch.profiles import STANDARD

SIGNED = replace(STANDARD, thousands_separator=",", currency_symbol="$", parentheses_negative=True)
EURO = replace(STANDARD, thousands_separator=".", decimal_separator=",")
DC_IN = replace(STANDARD, amount_column=None, debit_column="Debit", credit_column="Credit",
                debit_means="money-in")
DC_OUT = replace(DC_IN, debit_means="money-out")


class Dates(unittest.TestCase):
    def test_formats(self):
        us = replace(STANDARD, date_format="%m/%d/%Y")
        eu = replace(STANDARD, date_format="%d/%m/%Y")
        self.assertEqual(parse_date("03/04/2026", us), date(2026, 3, 4))
        self.assertEqual(parse_date("03/04/2026", eu), date(2026, 4, 3))  # same text, different day
        self.assertEqual(parse_date("04-Mar-2026", replace(STANDARD, date_format="%d-%b-%Y")), date(2026, 3, 4))
        self.assertEqual(parse_date("04-mar-2026", replace(STANDARD, date_format="%d-%b-%Y")), date(2026, 3, 4))
        self.assertEqual(parse_date(" 2026-03-04 ", STANDARD), date(2026, 3, 4))

    def test_wrong_order_for_profile_is_rejected(self):
        us = replace(STANDARD, date_format="%m/%d/%Y")
        with self.assertRaisesRegex(NormalizationError, "invalid date.*%m/%d/%Y.*01/31/2026"):
            parse_date("31/12/2026", us)  # a day-first date read with a month-first profile

    def test_impossible_and_malformed(self):
        for bad in ("2026-02-30", "2026-13-01", "", "x", "20260304", "2026-03-04 extra", "2026-W01-1"):
            with self.subTest(bad=bad), self.assertRaises(NormalizationError):
                parse_date(bad, STANDARD)

    def test_leading_zero_rule(self):
        us = replace(STANDARD, date_format="%m/%d/%Y")
        with self.assertRaisesRegex(NormalizationError, "zero_padded = false"):
            parse_date("3/4/2026", us)
        loose = replace(us, zero_padded=False)
        self.assertEqual(parse_date("3/4/2026", loose), date(2026, 3, 4))
        with self.assertRaises(NormalizationError):
            parse_date("3/45/2026", loose)

    def test_date_with_time_uses_the_date(self):
        p = replace(STANDARD, date_format="%Y-%m-%d %H:%M")
        self.assertEqual(parse_date("2026-03-04 14:05", p), date(2026, 3, 4))


class SignedAmounts(unittest.TestCase):
    def amount(self, text, profile=SIGNED):
        a = parse_signed_amount(text, profile)
        return a.value, a.text

    def test_plain_and_separators(self):
        self.assertEqual(self.amount("1,234.50"), (Decimal("1234.50"), "1234.50"))
        self.assertEqual(self.amount("-1,234.50"), (Decimal("-1234.50"), "-1234.50"))
        self.assertEqual(self.amount("12"), (Decimal("12"), "12"))
        self.assertEqual(self.amount("1,234,567.89")[0], Decimal("1234567.89"))

    def test_currency_symbol_positions(self):
        for text in ("$5.00", "-$5.00", "$-5.00", "$ 5.00"):
            with self.subTest(text=text):
                self.assertEqual(abs(self.amount(text)[0]), Decimal("5.00"))
        self.assertEqual(self.amount("-$5.00")[0], Decimal("-5.00"))
        self.assertEqual(self.amount("$-5.00")[0], Decimal("-5.00"))

    def test_parentheses_negative(self):
        self.assertEqual(self.amount("(5.00)"), (Decimal("-5.00"), "-5.00"))
        self.assertEqual(self.amount("($1,000.00)")[0], Decimal("-1000.00"))

    def test_trailing_zeros_survive(self):
        self.assertEqual(self.amount("10.10")[1], "10.10")
        self.assertEqual(self.amount("007.500")[1], "007.500")

    def test_zero_has_no_sign(self):
        self.assertEqual(self.amount("-0.00"), (Decimal("0.00"), "0.00"))
        self.assertEqual(self.amount("(0)")[1], "0")

    def test_rejected_forms(self):
        for bad in ("", "  ", "abc", "1,23", "12,34.50", "1,2345", ",500", "1,000,", "5.", ".5",
                    "5.00-", "5.00 CR", "5.00DR", "1e3", "NaN", "Infinity", "--5", "+5",
                    "(-5.00)", "(5.00", "5.00)", "€5", "$$5", "1 000", "1.000,00", "$"):
            with self.subTest(bad=bad), self.assertRaisesRegex(NormalizationError, "invalid amount"):
                parse_signed_amount(bad, SIGNED)

    def test_brackets_and_symbols_rejected_when_profile_does_not_allow_them(self):
        for bad in ("(5.00)", "$5.00", "1,000.00"):
            with self.subTest(bad=bad), self.assertRaises(NormalizationError):
                parse_signed_amount(bad, STANDARD)

    def test_decimal_comma_profile(self):
        self.assertEqual(self.amount("1.234,56", EURO), (Decimal("1234.56"), "1234.56"))
        self.assertEqual(self.amount("-0,99", EURO), (Decimal("-0.99"), "-0.99"))
        self.assertEqual(self.amount("1234,5", EURO)[0], Decimal("1234.5"))
        with self.assertRaises(NormalizationError):
            parse_signed_amount("1,234.56", EURO)  # wrong convention for this profile

    def test_inverted_sign(self):
        inv = replace(SIGNED, amount_sign="inverted")
        self.assertEqual(self.amount("25.00", inv), (Decimal("-25.00"), "-25.00"))
        self.assertEqual(self.amount("-25.00", inv), (Decimal("25.00"), "25.00"))
        self.assertEqual(self.amount("0.00", inv), (Decimal("0.00"), "0.00"))


class DebitCredit(unittest.TestCase):
    def test_direction_is_set_by_the_profile(self):
        # Cash account in the books: debit = money in.
        self.assertEqual(parse_debit_credit("50.00", "", DC_IN).value, Decimal("50.00"))
        self.assertEqual(parse_debit_credit("", "50.00", DC_IN).value, Decimal("-50.00"))
        # Bank wording: debit = money out.
        self.assertEqual(parse_debit_credit("50.00", "", DC_OUT).value, Decimal("-50.00"))
        self.assertEqual(parse_debit_credit("", "50.00", DC_OUT).value, Decimal("50.00"))

    def test_text_keeps_the_files_digits(self):
        self.assertEqual(parse_debit_credit("", "10.10", DC_IN).text, "-10.10")
        self.assertEqual(parse_debit_credit("10.10", "", DC_IN).text, "10.10")

    def test_both_filled_is_ambiguous(self):
        with self.assertRaisesRegex(NormalizationError, "both Debit .* and Credit .* contain amounts"):
            parse_debit_credit("5.00", "5.00", DC_IN)
        with self.assertRaises(NormalizationError):
            parse_debit_credit("5.00", "0.01", DC_IN)

    def test_both_blank_is_an_error(self):
        with self.assertRaisesRegex(NormalizationError, "both Debit and Credit are blank"):
            parse_debit_credit("", "  ", DC_IN)

    def test_zero_beside_a_real_amount_is_accepted(self):
        self.assertEqual(parse_debit_credit("0.00", "5.00", DC_IN).value, Decimal("-5.00"))
        self.assertEqual(parse_debit_credit("5.00", "0", DC_IN).value, Decimal("5.00"))

    def test_both_zero_is_zero(self):
        self.assertEqual(parse_debit_credit("0.00", "0.00", DC_IN).value, Decimal(0))
        self.assertEqual(parse_debit_credit("0", "", DC_IN).value, Decimal(0))

    def test_negative_numbers_in_columns_are_ambiguous(self):
        for debit, credit in (("-5.00", ""), ("", "-5.00")):
            with self.subTest(debit=debit, credit=credit):
                with self.assertRaisesRegex(NormalizationError, "negative value.*ambiguous"):
                    parse_debit_credit(debit, credit, DC_IN)
        brackets = replace(DC_IN, parentheses_negative=True)
        with self.assertRaisesRegex(NormalizationError, "ambiguous"):
            parse_debit_credit("(5.00)", "", brackets)

    def test_garbage_in_either_column(self):
        for debit, credit in (("abc", ""), ("", "$5"), ("5", "x")):
            with self.subTest(debit=debit, credit=credit), self.assertRaises(NormalizationError):
                parse_debit_credit(debit, credit, DC_IN)

    def test_separators_apply(self):
        p = replace(DC_IN, thousands_separator=",")
        self.assertEqual(parse_debit_credit("1,000.00", "", p).value, Decimal("1000.00"))


if __name__ == "__main__":
    unittest.main()
