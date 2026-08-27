"""Concurrency tests for per-user async locking."""

from __future__ import annotations

import asyncio
import importlib
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

app_mod = importlib.import_module("backend.app")
ss_mod = importlib.import_module("backend.sessions_store")
ul_mod = importlib.import_module("backend.user_locks")
us_mod = importlib.import_module("backend.user_state")


class UserLockTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        ul_mod._LOCKS.clear()

    async def test_same_user_session_writes_are_serialized(self) -> None:
        timeline: list[tuple[str, str, float]] = []
        active = 0
        max_active = 0
        active_guard = asyncio.Lock()

        original_append = ss_mod.append_message

        def slow_append(name, message, user_id=None):
            nonlocal active, max_active

            async def record_start() -> None:
                nonlocal active, max_active
                async with active_guard:
                    active += 1
                    max_active = max(max_active, active)
                    timeline.append((message["content"], "start", time.perf_counter()))

            async def record_end() -> None:
                nonlocal active
                async with active_guard:
                    timeline.append((message["content"], "end", time.perf_counter()))
                    active -= 1

            asyncio.run(record_start())
            time.sleep(0.05)
            result = original_append(name, message, user_id=user_id)
            asyncio.run(record_end())
            return result

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data_users_dir = tmp_path / "users"
            with patch.object(us_mod, "DATA_USERS_DIR", data_users_dir), patch.object(app_mod.sessions_store, "append_message", side_effect=slow_append):
                await asyncio.gather(
                    app_mod._append_session_message("main", {"role": "user", "content": "first"}, user_id="alice"),
                    app_mod._append_session_message("main", {"role": "assistant", "content": "second"}, user_id="alice"),
                )
                messages = ss_mod.load_session("main", user_id="alice")

        self.assertEqual(max_active, 1)
        self.assertEqual([item[0] for item in timeline], ["first", "first", "second", "second"])
        self.assertEqual([message["content"] for message in messages], ["first", "second"])

    async def test_different_users_can_write_concurrently(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        active = 0
        max_active = 0
        guard = asyncio.Lock()

        async def locked_write(user_id: str) -> str:
            nonlocal active, max_active

            async def operation() -> str:
                nonlocal active, max_active
                async with guard:
                    active += 1
                    max_active = max(max_active, active)
                    if active >= 2:
                        started.set()
                await release.wait()
                async with guard:
                    active -= 1
                return user_id

            return await ul_mod.run_with_user_lock(user_id, operation)

        task_a = asyncio.create_task(locked_write("alice"))
        task_b = asyncio.create_task(locked_write("bob"))

        await asyncio.wait_for(started.wait(), timeout=1)
        release.set()
        results = await asyncio.gather(task_a, task_b)

        self.assertEqual(set(results), {"alice", "bob"})
        self.assertGreaterEqual(max_active, 2)

    async def test_same_user_file_writes_are_serialized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            data_users_dir = project_root / "backend" / "data" / "users"
            target = data_users_dir / "alice" / "workspace" / "USER.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            (project_root / "backend" / "skills").mkdir(parents=True, exist_ok=True)

            original_write_text = Path.write_text
            active = 0
            max_active = 0
            guard = asyncio.Lock()

            def slow_write_text(path_obj: Path, content: str, *args, **kwargs):
                nonlocal active, max_active

                async def record_start() -> None:
                    nonlocal active, max_active
                    async with guard:
                        active += 1
                        max_active = max(max_active, active)

                async def record_end() -> None:
                    nonlocal active
                    async with guard:
                        active -= 1

                asyncio.run(record_start())
                time.sleep(0.05)
                result = original_write_text(path_obj, content, *args, **kwargs)
                asyncio.run(record_end())
                return result

            with patch.object(app_mod, "PROJECT_ROOT", project_root), patch.object(us_mod, "DATA_USERS_DIR", data_users_dir), patch.object(Path, "write_text", new=slow_write_text):
                await asyncio.gather(
                    app_mod.save_file(app_mod.FileWriteRequest(path="backend/data/users/alice/workspace/USER.md", content="first"), x_user_id="alice"),
                    app_mod.save_file(app_mod.FileWriteRequest(path="backend/data/users/alice/workspace/USER.md", content="second"), x_user_id="alice"),
                )

            self.assertEqual(max_active, 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "second")


if __name__ == "__main__":
    unittest.main()
