import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from ledgermatch.models import Transaction

HEADER = "date,description,amount\n"


def txn(day, amount, description="x", source="t.csv", line=2):
    """Build a Transaction quickly. `day` is 'YYYY-MM-DD', `amount` a string."""
    return Transaction(
        source=source, line=line, date=date.fromisoformat(day),
        description=description, amount=Decimal(amount), raw_date=day, amount_text=amount,
    )


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def write(self, name, text, encoding="utf-8"):
        path = self.tmp / name
        path.write_text(text, encoding=encoding, newline="")
        return path
