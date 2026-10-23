import json
import unittest
from actions.browser_control import browser_control, _registry

class TestBrowserRepair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure any existing test session is closed cleanly
        browser_control({"action": "close_all"})

    @classmethod
    def tearDownClass(cls):
        browser_control({"action": "close_all"})

    def test_01_navigation_and_structured_response(self):
        res_raw = browser_control({
            "action": "go_to",
            "browser": "chrome",
            "url": "https://example.com"
        })
        data = json.loads(res_raw)

        self.assertTrue(data.get("success"), f"Navigation failed: {res_raw}")
        self.assertTrue(data.get("verified"))
        self.assertEqual(data.get("operation"), "go_to")
        self.assertIn("example.com", data.get("url", ""))
        self.assertEqual(data.get("state"), "ready")
        self.assertIn("Example Domain", data.get("title", ""))

    def test_02_get_url_matches_active_page(self):
        res_raw = browser_control({
            "action": "get_url",
            "browser": "chrome"
        })
        data = json.loads(res_raw)

        self.assertTrue(data.get("success"))
        self.assertTrue(data.get("verified"))
        self.assertEqual(data.get("operation"), "get_url")
        self.assertIn("example.com", data.get("url", ""))

    def test_03_typing_into_input_and_verification(self):
        # Navigate to a page with an input field
        nav_raw = browser_control({
            "action": "go_to",
            "browser": "chrome",
            "url": "https://www.google.com"
        })
        nav_data = json.loads(nav_raw)
        self.assertTrue(nav_data.get("success"))

        # Type 'hello' without explicit selector (auto-detects input/textarea/composer)
        type_raw = browser_control({
            "action": "type",
            "browser": "chrome",
            "text": "hello",
            "clear_first": True,
            "press_enter": False
        })
        type_data = json.loads(type_raw)

        self.assertTrue(type_data.get("success"), f"Typing failed: {type_raw}")
        self.assertTrue(type_data.get("verified"), "Post-typing verification failed")
        self.assertEqual(type_data.get("typed_text"), "hello")
        self.assertIn("hello", type_data.get("observed_text", ""))
        self.assertFalse(type_data.get("press_enter"))
        self.assertIn("remains open", type_data.get("message", ""))

        # Verify browser remains open after typing
        url_raw = browser_control({"action": "get_url", "browser": "chrome"})
        url_data = json.loads(url_raw)
        self.assertTrue(url_data.get("success"))
        self.assertIn("google", url_data.get("url", ""))

    def test_04_error_reported_truthfully_on_invalid_action(self):
        res_raw = browser_control({
            "action": "non_existent_action_xyz",
            "browser": "chrome"
        })
        data = json.loads(res_raw)
        self.assertFalse(data.get("success"))
        self.assertFalse(data.get("verified"))
        self.assertIn("Unknown browser action", data.get("message", ""))

    def test_05_browser_closes_cleanly_when_requested(self):
        close_res = browser_control({"action": "close", "browser": "chrome"})
        self.assertIn("closed", close_res)

        list_res = browser_control({"action": "list_browsers"})
        self.assertIn("No active browser sessions", list_res)

if __name__ == "__main__":
    unittest.main()
