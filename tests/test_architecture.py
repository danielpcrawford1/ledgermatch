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

    def test_import_side_never_touches_the_engine(self):
        for name in ("profiles.py", "normalize.py", "loader.py"):
            mods = imported_modules(name)
            self.assertNotIn("ledgermatch.engine", mods, name)
            self.assertNotIn("ledgermatch.report", mods, name)
            self.assertNotIn("ledgermatch.cli", mods, name)

    def test_profiles_and_normalize_are_pure_configuration_and_parsing(self):
        self.assertFalse({m for m in imported_modules("profiles.py") if m.startswith("ledgermatch")})
        self.assertEqual({m for m in imported_modules("normalize.py") if m.startswith("ledgermatch")},
                         {"ledgermatch.profiles"})

    def test_report_does_not_depend_on_import_side_or_cli(self):
        mods = imported_modules("report.py")
        for banned in ("loader", "profiles", "normalize", "engine", "cli"):
            self.assertNotIn(f"ledgermatch.{banned}", mods)


if __name__ == "__main__":
    unittest.main()
