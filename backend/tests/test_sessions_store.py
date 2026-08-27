"""Unit tests for backend/sessions_store.py."""

from __future__ import annotations

import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Per the Codebase Pattern documented in US-008/US-011: use
# importlib.import_module so patch.object touches the real module attribute,
# not a name re-exported by `backend/__init__.py`.
ss_mod = importlib.import_module("backend.sessions_store")


class LoadSessionTests(unittest.TestCase):
    def test_missing_session_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ss_mod, "SESSIONS_DIR", Path(tmp)):
                self.assertEqual(ss_mod.load_session("never_created"), [])

    def test_loads_existing_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            (sessions_dir / "main.json").write_text(
                json.dumps(
                    [
                        {"role": "user", "content": "hi"},
                        {"role": "assistant", "content": "hello"},
                    ]
                ),
                encoding="utf-8",
            )
            with patch.object(ss_mod, "SESSIONS_DIR", sessions_dir):
                messages = ss_mod.load_session("main")

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1]["content"], "hello")

    def test_corrupt_json_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            (sessions_dir / "broken.json").write_text("not json{{{", encoding="utf-8")
            with patch.object(ss_mod, "SESSIONS_DIR", sessions_dir):
                self.assertEqual(ss_mod.load_session("broken"), [])

    def test_empty_file_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            (sessions_dir / "empty.json").write_text("", encoding="utf-8")
            with patch.object(ss_mod, "SESSIONS_DIR", sessions_dir):
                self.assertEqual(ss_mod.load_session("empty"), [])


class AppendMessageTests(unittest.TestCase):
    def test_append_creates_file_on_first_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp) / "sessions"  # dir does NOT pre-exist
            with patch.object(ss_mod, "SESSIONS_DIR", sessions_dir):
                self.assertFalse(sessions_dir.exists())
                result = ss_mod.append_message(
                    "fresh", {"role": "user", "content": "first"}
                )
                self.assertTrue(sessions_dir.exists())
                self.assertTrue((sessions_dir / "fresh.json").exists())
                self.assertEqual(result, [{"role": "user", "content": "first"}])

    def test_append_extends_existing_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            with patch.object(ss_mod, "SESSIONS_DIR", sessions_dir):
                ss_mod.append_message("chat", {"role": "user", "content": "ping"})
                ss_mod.append_message("chat", {"role": "assistant", "content": "pong"})
                ss_mod.append_message(
                    "chat",
                    {
                        "role": "tool",
                        "name": "terminal",
                        "tool_call_id": "call_1",
                        "content": "exit 0",
                    },
                )

                messages = ss_mod.load_session("chat")

        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[2]["role"], "tool")
        # Extra fields on tool messages round-trip verbatim.
        self.assertEqual(messages[2]["tool_call_id"], "call_1")
        self.assertEqual(messages[2]["name"], "terminal")

    def test_roundtrip_preserves_message_order_and_unicode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            with patch.object(ss_mod, "SESSIONS_DIR", sessions_dir):
                # Unicode + ordering check: ensure_ascii=False is respected.
                ss_mod.append_message(
                    "unicode", {"role": "user", "content": "你好"}
                )
                ss_mod.append_message(
                    "unicode", {"role": "assistant", "content": "👋"}
                )
                raw = (sessions_dir / "unicode.json").read_text(encoding="utf-8")
                messages = ss_mod.load_session("unicode")

        self.assertIn("你好", raw)  # not escaped
        self.assertIn("👋", raw)
        self.assertEqual([m["content"] for m in messages], ["你好", "👋"])

    def test_rejects_unknown_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ss_mod, "SESSIONS_DIR", Path(tmp)):
                with self.assertRaises(ValueError):
                    ss_mod.append_message(
                        "bad", {"role": "system", "content": "nope"}
                    )

    def test_rejects_non_dict_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ss_mod, "SESSIONS_DIR", Path(tmp)):
                with self.assertRaises(TypeError):
                    ss_mod.append_message("bad", "not a dict")  # type: ignore[arg-type]


class SessionNameValidationTests(unittest.TestCase):
    def test_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ss_mod, "SESSIONS_DIR", Path(tmp)):
                for bad in ("../escape", "a/b", "..", ".", "", "with space"):
                    with self.subTest(name=bad):
                        with self.assertRaises(ValueError):
                            ss_mod.load_session(bad)
                        with self.assertRaises(ValueError):
                            ss_mod.append_message(
                                bad, {"role": "user", "content": "x"}
                            )

    def test_accepts_typical_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ss_mod, "SESSIONS_DIR", Path(tmp)):
                for ok in ("main_session", "main-session", "session.1", "abc123"):
                    with self.subTest(name=ok):
                        # load on a missing session must return [] without raising
                        self.assertEqual(ss_mod.load_session(ok), [])


if __name__ == "__main__":
    unittest.main()
