"""Unit tests for the sandboxed terminal tool (US-004)."""

from __future__ import annotations

import unittest

from backend.tools.terminal import BLOCKED_MESSAGE, _is_blacklisted, terminal


class BlacklistDetectionTests(unittest.TestCase):
    def test_blacklist_catches_documented_patterns(self) -> None:
        for cmd in (
            "rm -rf /",
            "rm -rf /etc",
            "rm -rf ~",
            "rm -rf ~/Documents",
            ":(){ :|:& };:",
            "mkfs.ext4 /dev/sda1",
            "dd if=/dev/zero of=/dev/sda",
        ):
            with self.subTest(cmd=cmd):
                self.assertTrue(_is_blacklisted(cmd))

    def test_blacklist_lets_safe_commands_through(self) -> None:
        for cmd in (
            "echo hello",
            "ls -la",
            "rm -i tmpfile",
            "python3 -c 'print(1)'",
            "grep -r foo backend",
        ):
            with self.subTest(cmd=cmd):
                self.assertFalse(_is_blacklisted(cmd))


class TerminalToolInvocationTests(unittest.TestCase):
    def test_allowed_command_runs_and_returns_output(self) -> None:
        out = terminal.invoke({"command": "echo hello-mini-openclaw"})
        self.assertIn("hello-mini-openclaw", out)

    def test_invalid_command_returns_shell_error_output(self) -> None:
        out = terminal.invoke({"command": "definitely_not_a_real_command_12345"})
        lowered = out.lower()
        self.assertTrue(
            "not found" in lowered or "no such file" in lowered or "is not recognized" in lowered
        )

    def test_blacklisted_command_is_refused_without_executing(self) -> None:
        out = terminal.invoke({"command": "rm -rf /"})
        self.assertEqual(out, BLOCKED_MESSAGE)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
