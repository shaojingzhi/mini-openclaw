"""Unit tests for the sandboxed terminal tool (US-004)."""

from __future__ import annotations

import unittest

from backend.tools.terminal import (
    BLOCKED_MESSAGE,
    SCOPED_BLOCKED_MESSAGE,
    _is_agent_safe_command,
    _is_blacklisted,
    build_terminal_tool,
    terminal,
)


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


class AgentScopedTerminalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.terminal = build_terminal_tool(agent_id="spark")

    def test_allows_auditable_commands(self) -> None:
        self.assertTrue(self.terminal.invoke({"command": "pwd"}).strip())
        own_path = "backend/memory/approved_memory/agents/spark"
        self.assertNotEqual(
            self.terminal.invoke({"command": f"ls {own_path}"}),
            SCOPED_BLOCKED_MESSAGE,
        )

    def test_rejects_non_allowlisted_and_shell_commands(self) -> None:
        for command in (
            "cat README.md",
            "pwd | cat",
            "pwd > /tmp/agent-output",
        ):
            with self.subTest(command=command):
                self.assertEqual(
                    self.terminal.invoke({"command": command}),
                    SCOPED_BLOCKED_MESSAGE,
                )

    def test_rejects_other_agent_private_projection(self) -> None:
        commands = (
            "ls backend/memory/approved_memory/agents/whetstone",
            "ls backend/memory/approved_memory/agents/spark/../whetstone",
            "ls backend/memory/approved_memory/agents",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(
                    self.terminal.invoke({"command": command}),
                    SCOPED_BLOCKED_MESSAGE,
                )

    def test_frontend_npm_allowlist_requires_exact_prefix_and_script(self) -> None:
        self.assertTrue(
            _is_agent_safe_command(
                ["npm", "--prefix", "frontend", "run", "typecheck"],
                agent_id="spark",
            )
        )
        self.assertFalse(
            _is_agent_safe_command(
                ["npm", "--prefix", "../other-project", "run", "typecheck"],
                agent_id="spark",
            )
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
