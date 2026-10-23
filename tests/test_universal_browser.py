"""
Test Suite: Universal Browser Integration for JARVIS (MARK-LVI)
Tests:
- Dynamic installed browser detection
- System default browser discovery
- Spoken browser name normalization
- URL shorthand and service resolution (Gmail, LinkedIn, YouTube, GitHub, etc.)
- Native browser launching preserving real user profiles
- Graceful fallback for uninstalled browsers (e.g. Firefox when not installed)
- Last visited website memory and reopen functionality ('open_last')
- Web search query execution in user's browser
"""

import json
import unittest
from pathlib import Path
from actions.browser_control import browser_control
from core.browser_manager import browser_mgr, BrowserManager


class TestUniversalBrowserIntegration(unittest.TestCase):

    def test_01_installed_browsers_discovery(self):
        """Verifies that installed Windows browsers are detected dynamically."""
        installed = browser_mgr.get_installed_browsers(force_refresh=True)
        self.assertIsInstance(installed, dict)
        self.assertGreaterEqual(len(installed), 1, "At least one browser must be installed")
        
        # Verify schema
        for key, info in installed.items():
            self.assertIn("key", info)
            self.assertIn("display_name", info)
            self.assertIn("exe_path", info)
            self.assertTrue(Path(info["exe_path"]).exists(), f"Exe not found: {info['exe_path']}")

        # Ensure summary string can be retrieved
        summary = browser_mgr.list_installed_summary()
        self.assertTrue(summary.get("success"))
        self.assertIn("Installed Browsers", summary.get("summary_text", ""))

    def test_02_default_browser_detection(self):
        """Verifies that the system default browser is identified."""
        default_browser = browser_mgr.detect_default_browser()
        self.assertIn(default_browser, ["edge", "chrome", "firefox", "brave", "opera", "safari", "vivaldi"])
        
        # Check action call
        res_raw = browser_control({"action": "list_browsers"})
        data = json.loads(res_raw)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("default_browser"), default_browser)

    def test_03_browser_name_normalization(self):
        """Tests that spoken variations correctly map to canonical keys."""
        cases = [
            ("Google Chrome", "chrome"),
            ("google-chrome", "chrome"),
            ("Microsoft Edge", "edge"),
            ("MS Edge", "edge"),
            ("msedge", "edge"),
            ("Mozilla Firefox", "firefox"),
            ("ff", "firefox"),
            ("Brave Browser", "brave"),
            ("Opera GX", "operagx"),
            ("my default browser", "default"),
            ("in chrome", "chrome"),
            ("on edge", "edge"),
        ]
        for spoken, expected in cases:
            norm = browser_mgr.normalize_browser_name(spoken)
            self.assertEqual(norm, expected, f"Failed to normalize '{spoken}' to '{expected}'")

    def test_04_website_url_resolution(self):
        """Tests that popular website shorthand and shortcuts map to real URLs."""
        test_cases = [
            ("gmail", "https://mail.google.com"),
            ("linkedin", "https://www.linkedin.com"),
            ("youtube", "https://www.youtube.com"),
            ("github", "https://github.com"),
            ("chatgpt", "https://chatgpt.com"),
            ("leetcode", "https://leetcode.com"),
            ("striver", "https://takeuforward.org"),
            ("https://example.com/test", "https://example.com/test"),
            ("github.com/torvalds/linux", "https://github.com/torvalds/linux"),
        ]
        for shorthand, expected in test_cases:
            resolved = browser_mgr.resolve_url(shorthand)
            self.assertEqual(resolved, expected, f"Failed to resolve '{shorthand}' -> '{expected}'")

    def test_05_uninstalled_browser_graceful_fallback(self):
        """
        When the user requests an uninstalled browser (e.g. Firefox on a system without it),
        JARVIS must report that it is unavailable and open in default browser as an alternative.
        """
        installed = browser_mgr.get_installed_browsers()
        # Find a browser that is definitely not installed
        uninstalled_candidate = None
        for cand in ["firefox", "operagx", "vivaldi", "arc"]:
            if cand not in installed:
                uninstalled_candidate = cand
                break
        
        if uninstalled_candidate:
            res_raw = browser_control({
                "action": "open",
                "browser": uninstalled_candidate,
                "url": "https://example.com"
            })
            data = json.loads(res_raw)
            self.assertTrue(data.get("success"), f"Launch failed: {res_raw}")
            self.assertTrue(data.get("fallback_used"), "Fallback to default was not flagged")
            self.assertIn("not installed", data.get("message", "").lower())
            self.assertIn("default browser", data.get("message", "").lower())

    def test_06_visit_history_and_open_last(self):
        """Tests tracking visited sites and reopening via 'open_last'."""
        target_url = "https://github.com"
        # Record a visit
        browser_mgr.record_visit(target_url, "chrome", "GitHub")
        
        last = browser_mgr.get_last_visited()
        self.assertIsNotNone(last)
        self.assertEqual(last.get("url"), target_url)

        # Reopen last visited via browser_control
        res_raw = browser_control({"action": "open_last"})
        data = json.loads(res_raw)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("operation"), "open_last")
        self.assertEqual(data.get("last_visited_url"), target_url)

    def test_07_search_in_browser(self):
        """Tests web search in browser preserving existing session."""
        res_raw = browser_control({
            "action": "search",
            "browser": "default",
            "query": "Python tutorials",
            "engine": "google"
        })
        data = json.loads(res_raw)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("operation"), "search")
        self.assertIn("google.com/search?q=Python+tutorials", data.get("url", ""))
        self.assertTrue(data.get("reused_session"))

    def test_08_native_open_website_preserves_profile(self):
        """Verifies native opening marks reused_session=True and runs cleanly."""
        res_raw = browser_control({
            "action": "open",
            "browser": "chrome",
            "url": "linkedin"
        })
        data = json.loads(res_raw)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("operation"), "open")
        self.assertEqual(data.get("url"), "https://www.linkedin.com")
        self.assertTrue(data.get("reused_session"))


if __name__ == "__main__":
    unittest.main()
