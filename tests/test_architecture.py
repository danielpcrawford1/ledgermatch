"""Guards the module boundaries described in docs/ARCHITECTURE.md."""

import ast
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "src" / "ledgermatch"


def imported_modules(filename):
    tree = ast.parse((PKG / filename).read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


class ModuleBoundaries(unittest.TestCase):
    def test_models_imports_nothing_from_the_package(self):
        self.assertFalse({m for m in imported_modules("models.py") if m.startswith("ledgermatch")})

    def test_engine_is_pure_logic(self):
        allowed = {"collections", "collections.abc", "datetime", "decimal", "ledgermatch.models"}
        self.assertLessEqual(imported_modules("engine.py"), allowed)

    def test_loader_and_report_do_not_depend_on_each_other_or_cli(self):
        for name in ("loader.py", "report.py"):
            mods = imported_modules(name)
            self.assertFalse({"ledgermatch.cli", "ledgermatch.loader", "ledgermatch.report"} & mods, name)
            self.assertNotIn("ledgermatch.engine", mods, name)


if __name__ == "__main__":
    unittest.main()
