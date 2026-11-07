import random
import unittest
from decimal import Decimal

from helpers import txn
from ledgermatch.engine import reconcile


class MatchingRules(unittest.TestCase):
    def test_exact_date_and_amount_match(self):
        r = reconcile([txn("2026-01-05", "-86.40")], [txn("2026-01-05", "-86.40")])
        self.assertEqual((len(r.matches), r.bank_only, r.register_only), (1, [], []))

    def test_description_is_never_used(self):
        # Same description, different amount: no match.
        r = reconcile([txn("2026-01-05", "10.00", "Rent")],
                      [txn("2026-01-05", "10.01", "Rent")])
        self.assertEqual(len(r.matches), 0)
        # Completely different descriptions, same date and amount: match.
        r = reconcile([txn("2026-01-05", "10.00", "AAA")],
                      [txn("2026-01-05", "10.00", "ZZZ")])
        self.assertEqual(len(r.matches), 1)

    def test_one_day_apart_does_not_match(self):
        r = reconcile([txn("2026-01-05", "5.00")], [txn("2026-01-06", "5.00")])
        self.assertEqual((len(r.bank_only), len(r.register_only)), (1, 1))

    def test_negative_amounts_are_distinct_from_positive(self):
        r = reconcile([txn("2026-01-01", "-20.00")],
                      [txn("2026-01-01", "20.00"), txn("2026-01-01", "-20.00", line=3)])
        self.assertEqual(len(r.matches), 1)
        self.assertEqual(r.matches[0].register.amount, Decimal("-20.00"))
        self.assertEqual(r.register_only[0].amount, Decimal("20.00"))

    def test_decimal_exactness(self):
        # 10.10 and 10.1 are the same money; one cent apart is not.
        self.assertEqual(len(reconcile([txn("2026-01-01", "10.10")],
                                       [txn("2026-01-01", "10.1")]).matches), 1)
        self.assertEqual(len(reconcile([txn("2026-01-01", "10.10")],
                                       [txn("2026-01-01", "10.11")]).matches), 0)
        # Floats would fail this: 0.1 + 0.2 != 0.3.
        self.assertEqual(Decimal("0.1") + Decimal("0.2"), Decimal("0.3"))

    def test_empty_inputs(self):
        r = reconcile([], [])
        self.assertEqual((r.matches, r.bank_only, r.register_only, r.ambiguous_groups),
                         ([], [], [], {}))
        r = reconcile([txn("2026-01-01", "1.00")], [])
        self.assertEqual(len(r.bank_only), 1)
        r = reconcile([], [txn("2026-01-01", "1.00")])
        self.assertEqual(len(r.register_only), 1)


class Duplicates(unittest.TestCase):
    def test_extra_bank_duplicate_is_reported_and_flagged(self):
        bank = [txn("2026-01-01", "5.00", line=i) for i in (2, 3, 4)]
        register = [txn("2026-01-01", "5.00", line=i) for i in (2, 3)]
        r = reconcile(bank, register)
        self.assertEqual(len(r.matches), 2)
        self.assertEqual([t.line for t in r.bank_only], [4])
        self.assertEqual(r.register_only, [])
        self.assertTrue(all(m.ambiguous for m in r.matches))
        group = r.ambiguous_groups[(bank[0].date, Decimal("5.00"))]
        self.assertEqual((group.bank_count, group.register_count), (3, 2))

    def test_extra_register_duplicate(self):
        r = reconcile([txn("2026-01-01", "5.00")],
                      [txn("2026-01-01", "5.00", line=i) for i in (2, 3, 4)])
        self.assertEqual((len(r.matches), len(r.register_only)), (1, 2))
        self.assertEqual(len(r.ambiguous_groups), 1)

    def test_register_row_never_used_twice(self):
        bank = [txn("2026-01-01", "5.00", line=i) for i in range(2, 7)]
        register = [txn("2026-01-01", "5.00", line=i) for i in range(2, 4)]
        r = reconcile(bank, register)
        used = [m.register.line for m in r.matches]
        self.assertEqual(len(used), len(set(used)))

    def test_pairing_follows_file_order(self):
        bank = [txn("2026-01-01", "5.00", "b1", line=2), txn("2026-01-01", "5.00", "b2", line=3)]
        register = [txn("2026-01-01", "5.00", "r1", line=2), txn("2026-01-01", "5.00", "r2", line=3)]
        r = reconcile(bank, register)
        self.assertEqual([(m.bank.description, m.register.description) for m in r.matches],
                         [("b1", "r1"), ("b2", "r2")])

    def test_unmatched_duplicates_are_not_flagged_as_ambiguous(self):
        # Two identical bank rows and nothing in the register: nothing to choose between.
        r = reconcile([txn("2026-01-01", "5.00", line=2), txn("2026-01-01", "5.00", line=3)], [])
        self.assertEqual(len(r.bank_only), 2)
        self.assertEqual(r.ambiguous_groups, {})

    def test_single_unique_match_is_not_flagged(self):
        r = reconcile([txn("2026-01-01", "5.00")], [txn("2026-01-01", "5.00")])
        self.assertFalse(r.matches[0].ambiguous)


class Invariants(unittest.TestCase):
    """Property-style checks on random data: no row is lost, invented or reused."""

    def test_every_row_accounted_for_exactly_once(self):
        rng = random.Random(20260307)
        days = ["2026-03-01", "2026-03-02", "2026-03-03"]
        amounts = ["1.00", "-1.00", "2.50", "0"]
        for _ in range(300):
            bank = [txn(rng.choice(days), rng.choice(amounts), line=i + 2)
                    for i in range(rng.randint(0, 12))]
            register = [txn(rng.choice(days), rng.choice(amounts), line=i + 2)
                        for i in range(rng.randint(0, 12))]
            r = reconcile(bank, register)

            bank_seen = [m.bank.line for m in r.matches] + [t.line for t in r.bank_only]
            reg_seen = [m.register.line for m in r.matches] + [t.line for t in r.register_only]
            self.assertEqual(sorted(bank_seen), sorted(t.line for t in bank))
            self.assertEqual(sorted(reg_seen), sorted(t.line for t in register))
            for m in r.matches:
                self.assertEqual((m.bank.date, m.bank.amount),
                                 (m.register.date, m.register.amount))
            # Control totals agree.
            self.assertEqual(
                sum((m.bank.amount for m in r.matches), Decimal(0))
                + sum((t.amount for t in r.bank_only), Decimal(0)),
                sum((t.amount for t in bank), Decimal(0)))

    def test_inputs_are_not_modified(self):
        bank = [txn("2026-01-01", "5.00")]
        register = [txn("2026-01-01", "5.00")]
        bank_copy, register_copy = list(bank), list(register)
        reconcile(bank, register)
        self.assertEqual((bank, register), (bank_copy, register_copy))


if __name__ == "__main__":
    unittest.main()
