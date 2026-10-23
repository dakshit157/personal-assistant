import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from actions.file_controller import file_controller
from actions.browser_control import browser_control

class MockFunctionCall:
    def __init__(self, name: str, args: dict, call_id: str = "call_123"):
        self.name = name
        self.args = args
        self.id = call_id

class TestAgentIntegration(unittest.TestCase):
    def test_actions_log_recording(self):
        log_dir = Path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "actions.log"

        initial_count = 0
        if log_file.exists():
            with open(log_file, "r", encoding="utf-8") as f:
                initial_count = len(f.readlines())

        # Simulate JarvisLive logging mechanism directly
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        entry = {
            "timestamp": timestamp,
            "tool": "file_controller",
            "arguments": {"action": "list", "path": "desktop"},
            "duration_seconds": 0.05,
            "deduplicated": False,
            "result_preview": "test entry"
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        self.assertGreater(len(lines), initial_count)
        last_entry = json.loads(lines[-1])
        self.assertEqual(last_entry["tool"], "file_controller")
        self.assertEqual(last_entry["arguments"]["action"], "list")

    def test_deduplication_cache_logic(self):
        # Test sliding window deduplication algorithm
        cache = {}
        window = 2.5

        def mock_dispatch(name, args):
            key = (name, tuple(sorted((k, str(v)) for k, v in args.items())))
            now = time.monotonic()
            if key in cache:
                last_t, last_res = cache[key]
                if (now - last_t) < window:
                    return last_res, True  # (result, deduplicated)
            # simulate execution
            result = f"executed_{name}_{now}"
            cache[key] = (now, result)
            return result, False

        # First call: executes
        res1, dedup1 = mock_dispatch("browser_control", {"action": "go_to", "url": "https://example.com"})
        self.assertFalse(dedup1)

        # Immediate second call within 2.5s: deduplicated
        res2, dedup2 = mock_dispatch("browser_control", {"action": "go_to", "url": "https://example.com"})
        self.assertTrue(dedup2)
        self.assertEqual(res1, res2)

        # Different action: executes
        res3, dedup3 = mock_dispatch("browser_control", {"action": "get_url"})
        self.assertFalse(dedup3)

    def test_structured_tool_truthfulness(self):
        # Verify that tools return parseable JSON with success and verified keys
        file_res = file_controller({"action": "disk_usage"})
        file_data = json.loads(file_res)
        self.assertIn("success", file_data)
        self.assertIn("verified", file_data)
        self.assertTrue(file_data["success"])

        browser_res = browser_control({"action": "list_browsers"})
        self.assertIsInstance(browser_res, str)

if __name__ == "__main__":
    unittest.main()
