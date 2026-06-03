"""Unit tests for the python_repl agent tool (US-005)."""

from __future__ import annotations

import unittest

from backend.tools.python_repl import python_repl


class PythonReplToolTests(unittest.TestCase):
    def test_print_two_plus_two_returns_four(self) -> None:
        out = python_repl.invoke({"query": "print(2+2)"})
        self.assertEqual(out, "4")

    def test_arithmetic_chain(self) -> None:
        out = python_repl.invoke({"query": "print((3 * 7) - 1)"})
        self.assertEqual(out, "20")

    def test_import_math_and_use_it(self) -> None:
        out = python_repl.invoke(
            {"query": "import math\nprint(math.sqrt(16))\nprint(math.floor(3.7))"}
        )
        self.assertEqual(out.splitlines(), ["4.0", "3"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
