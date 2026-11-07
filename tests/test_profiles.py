import unittest
from pathlib import Path

from helpers import TempDirCase
from ledgermatch.profiles import STANDARD, ProfileError, load_profile

SAMPLE_PROFILES = Path(__file__).resolve().parent.parent / "sample_data" / "profiles"

VALID = """
[columns]
date = "Date"
amount = "Amt"
"""


class Loading(TempDirCase):
    def profile(self, text):
        return load_profile(str(self.write("p.toml", text)))

    def assertRejects(self, text, pattern):
        with self.assertRaisesRegex(ProfileError, pattern):
            self.profile(text)

    def test_builtin_standard(self):
        self.assertIs(load_profile("standard"), STANDARD)
        self.assertEqual(STANDARD.extra_columns, "error")

    def test_sample_profiles_load(self):
        signed = load_profile(str(SAMPLE_PROFILES / "credit-union-signed.toml"))
        self.assertEqual((signed.skip_rows, signed.date_format), (2, "%m/%d/%Y"))
        ledger = load_profile(str(SAMPLE_PROFILES / "ledger-debit-credit.toml"))
        self.assertEqual((ledger.debit_column, ledger.debit_means), ("Debit", "money-in"))

    def test_minimal_profile_gets_defaults_and_file_stem_name(self):
        p = self.profile(VALID)
        self.assertEqual((p.name, p.date_format, p.extra_columns, p.description_columns),
                         ("p", "%Y-%m-%d", "preserve", ()))

    def test_unknown_profile_name(self):
        with self.assertRaisesRegex(ProfileError, "not found"):
            load_profile("nosuchbank")

    def test_invalid_toml(self):
        self.assertRejects("[columns\ndate=", "not valid TOML")

    def test_typos_are_errors_not_ignored(self):
        self.assertRejects(VALID + '\n[amounts]\nthousand_separator = ","\n', "unknown setting.*thousand_separator")
        self.assertRejects(VALID + "\n[dates]\nformt = 'x'\n", "unknown setting.*formt")
        self.assertRejects(VALID + "\n[extra]\nx = 1\n", "unknown setting")
        self.assertRejects('[columns]\ndate="D"\namout="A"\n', "unknown setting.*amout")

    def test_required_columns(self):
        self.assertRejects('[columns]\namount = "A"\n', "date is required")
        self.assertRejects('[columns]\ndate = "D"\n', "either amount, or both debit and credit")
        self.assertRejects('[columns]\ndate="D"\ndebit="Dr"\n', "both debit and credit")

    def test_amount_and_debit_credit_are_exclusive(self):
        self.assertRejects('[columns]\ndate="D"\namount="A"\ndebit="X"\ncredit="Y"\n', "not both")

    def test_debit_meaning_must_be_stated(self):
        base = '[columns]\ndate="D"\ndebit="Dr"\ncredit="Cr"\n'
        self.assertRejects(base, "debit_means is required")
        self.assertRejects(base + '[amounts]\ndebit_means = "bank"\n', "debit_means must be one of")
        ok = self.profile(base + '[amounts]\ndebit_means = "money-out"\n')
        self.assertEqual(ok.debit_means, "money-out")

    def test_debit_means_rejected_for_single_amount_column(self):
        self.assertRejects(VALID + '[amounts]\ndebit_means = "money-in"\n', "only with debit/credit")

    def test_amount_sign_rejected_for_debit_credit(self):
        self.assertRejects('[columns]\ndate="D"\ndebit="Dr"\ncredit="Cr"\n'
                           '[amounts]\ndebit_means="money-in"\namount_sign="inverted"\n',
                           "single amount column")

    def test_same_column_used_twice(self):
        self.assertRejects('[columns]\ndate="X"\namount="x"\n', "used only once")
        self.assertRejects('[columns]\ndate="D"\ndescription=["M","m"]\namount="A"\n', "used only once")

    def test_date_format_rules(self):
        for bad in ("%d/%m/%y", "%m/%d", "%Y-%m", "%Y", "nothing"):
            with self.subTest(fmt=bad):
                self.assertRejects(VALID + f'[dates]\nformat = "{bad}"\n', "date format")
        for good in ("%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%B %d, %Y", "%Y-%m-%d %H:%M"):
            with self.subTest(fmt=good):
                self.assertEqual(self.profile(VALID + f'[dates]\nformat = "{good}"\n').date_format, good)

    def test_separators(self):
        self.assertRejects(VALID + '[amounts]\nthousands_separator="."\ndecimal_separator="."\n', "must differ")
        self.assertRejects(VALID + '[amounts]\nthousands_separator=";"\n', "thousands_separator must be one of")
        self.assertRejects(VALID + '[amounts]\ncurrency_symbol="$ 1"\n', "currency_symbol")

    def test_file_settings(self):
        self.assertRejects(VALID + '[file]\ndelimiter=";;"\n', "single character")
        self.assertRejects(VALID + '[file]\nskip_rows=-1\n', "negative")
        self.assertRejects(VALID + '[file]\nskip_rows="2"\n', "skip_rows must be int")
        self.assertRejects(VALID + '[file]\nskip_rows=true\n', "skip_rows must be int")
        self.assertRejects(VALID + '[file]\nencoding="klingon"\n', "unknown encoding")
        self.assertRejects(VALID + '[file]\nextra_columns="drop"\n', "extra_columns must be one of")

    def test_wrong_types(self):
        self.assertRejects('[columns]\ndate=1\namount="A"\n', "date must be str")
        self.assertRejects(VALID + '[amounts]\nparentheses_negative="yes"\n', "must be bool")


if __name__ == "__main__":
    unittest.main()
