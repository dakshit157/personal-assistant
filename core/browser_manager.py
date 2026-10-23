"""
Universal Browser Manager for JARVIS (MARK-LVI)
-----------------------------------------------
Discovers all installed browsers across Windows, macOS, and Linux,
maps voice and text queries to executables, resolves web URLs,
launches browsers natively with the user's REAL default profiles and
active sessions (preserving cookies, logins, extensions, and bookmarks),
and maintains visit history for commands like "Open the last website I visited".
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

# Directory where browser visit history is stored
_MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"
_HISTORY_FILE = _MEMORY_DIR / "browser_history.json"


# Canonical browser metadata and known registry/executable identifiers
BROWSER_METADATA: dict[str, dict[str, Any]] = {
    "chrome": {
        "display_name": "Google Chrome",
        "win_exes": ["chrome.exe"],
        "win_app_paths": ["chrome.exe"],
        "win_start_menu": ["Google Chrome", "Google Chrome.exe", "Chrome"],
        "mac_apps": ["Google Chrome.app"],
        "linux_bins": ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"],
        "default_keywords": ["chrome"],
    },
    "edge": {
        "display_name": "Microsoft Edge",
        "win_exes": ["msedge.exe"],
        "win_app_paths": ["msedge.exe"],
        "win_start_menu": ["Microsoft Edge", "Microsoft Edge.exe", "msedge"],
        "mac_apps": ["Microsoft Edge.app"],
        "linux_bins": ["microsoft-edge", "microsoft-edge-stable"],
        "default_keywords": ["edge", "msedgehtm"],
    },
    "brave": {
        "display_name": "Brave Browser",
        "win_exes": ["brave.exe"],
        "win_app_paths": ["brave.exe"],
        "win_start_menu": ["Brave", "Brave-Browser", "Brave.exe"],
        "mac_apps": ["Brave Browser.app"],
        "linux_bins": ["brave-browser", "brave"],
        "default_keywords": ["brave", "bravehtml"],
    },
    "firefox": {
        "display_name": "Mozilla Firefox",
        "win_exes": ["firefox.exe"],
        "win_app_paths": ["firefox.exe"],
        "win_start_menu": ["Mozilla Firefox", "Firefox", "FIREFOX.EXE"],
        "mac_apps": ["Firefox.app"],
        "linux_bins": ["firefox"],
        "default_keywords": ["firefox", "firefoxurl"],
    },
    "opera": {
        "display_name": "Opera",
        "win_exes": ["opera.exe"],
        "win_app_paths": ["opera.exe"],
        "win_start_menu": ["OperaStable", "Opera", "opera.exe"],
        "mac_apps": ["Opera.app"],
        "linux_bins": ["opera", "opera-stable"],
        "default_keywords": ["opera", "operastable"],
    },
    "operagx": {
        "display_name": "Opera GX",
        "win_exes": ["opera.exe"],
        "win_app_paths": ["opera.exe"],
        "win_start_menu": ["OperaGXStable", "Opera GX", "operagx.exe"],
        "mac_apps": ["Opera GX.app"],
        "linux_bins": ["opera-gx", "opera"],
        "default_keywords": ["operagx", "operagxstable"],
    },
    "vivaldi": {
        "display_name": "Vivaldi",
        "win_exes": ["vivaldi.exe"],
        "win_app_paths": ["vivaldi.exe"],
        "win_start_menu": ["Vivaldi", "vivaldi.exe"],
        "mac_apps": ["Vivaldi.app"],
        "linux_bins": ["vivaldi", "vivaldi-stable"],
        "default_keywords": ["vivaldi", "vivaldihtm"],
    },
    "arc": {
        "display_name": "Arc",
        "win_exes": ["Arc.exe"],
        "win_app_paths": ["Arc.exe"],
        "win_start_menu": ["Arc", "Arc.exe"],
        "mac_apps": ["Arc.app"],
        "linux_bins": ["arc"],
        "default_keywords": ["arc", "archtm"],
    },
    "safari": {
        "display_name": "Safari",
        "win_exes": [],
        "win_app_paths": [],
        "win_start_menu": [],
        "mac_apps": ["Safari.app"],
        "linux_bins": [],
        "default_keywords": ["safari"],
    },
}

# Spoken and written aliases mapped to canonical keys
BROWSER_ALIASES: dict[str, str] = {
    "google chrome": "chrome",
    "google-chrome": "chrome",
    "chrome": "chrome",
    "gchrome": "chrome",
    "microsoft edge": "edge",
    "ms edge": "edge",
    "msedge": "edge",
    "edge": "edge",
    "brave": "brave",
    "brave browser": "brave",
    "mozilla firefox": "firefox",
    "mozilla": "firefox",
    "firefox": "firefox",
    "ff": "firefox",
    "opera": "opera",
    "opera browser": "opera",
    "opera gx": "operagx",
    "opera_gx": "operagx",
    "operagx": "operagx",
    "gx": "operagx",
    "vivaldi": "vivaldi",
    "vivaldi browser": "vivaldi",
    "arc": "arc",
    "arc browser": "arc",
    "safari": "safari",
    "apple safari": "safari",
    "default": "default",
    "my default": "default",
    "default browser": "default",
    "system default": "default",
    "my default browser": "default",
}

# Common website names and service shortcuts mapped to real URLs
WEBSITE_SHORTCUTS: dict[str, str] = {
    "gmail": "https://mail.google.com",
    "google mail": "https://mail.google.com",
    "linkedin": "https://www.linkedin.com",
    "youtube": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "github": "https://github.com",
    "git hub": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "chat gpt": "https://chatgpt.com",
    "openai": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "gemini": "https://gemini.google.com",
    "google": "https://www.google.com",
    "google search": "https://www.google.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "reddit": "https://www.reddit.com",
    "whatsapp": "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
    "telegram": "https://web.telegram.org",
    "telegram web": "https://web.telegram.org",
    "instagram": "https://www.instagram.com",
    "ig": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "fb": "https://www.facebook.com",
    "netflix": "https://www.netflix.com",
    "spotify": "https://open.spotify.com",
    "spotify web": "https://open.spotify.com",
    "leetcode": "https://leetcode.com",
    "leet code": "https://leetcode.com",
    "takeuforward": "https://takeuforward.org",
    "take u forward": "https://takeuforward.org",
    "striver": "https://takeuforward.org",
    "striver sheet": "https://takeuforward.org/strivers-a2z-dsa-course/strivers-a2z-dsa-course-sheet-2/",
    "geeksforgeeks": "https://www.geeksforgeeks.org",
    "gfg": "https://www.geeksforgeeks.org",
    "hackerrank": "https://www.hackerrank.com",
    "codeforces": "https://codeforces.com",
    "amazon": "https://www.amazon.in",
    "flipkart": "https://www.flipkart.com",
    "google drive": "https://drive.google.com",
    "drive": "https://drive.google.com",
    "google docs": "https://docs.google.com",
    "docs": "https://docs.google.com",
    "google maps": "https://maps.google.com",
    "maps": "https://maps.google.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "notion": "https://www.notion.so",
    "discord": "https://discord.com/app",
}

SEARCH_ENGINES: dict[str, str] = {
    "google": "https://www.google.com/search?q=",
    "bing": "https://www.bing.com/search?q=",
    "duckduckgo": "https://duckduckgo.com/?q=",
    "yandex": "https://yandex.com/search/?text=",
}


class BrowserManager:
    """Centralized manager for browser detection, launch, navigation, and history."""

    _instance: Optional[BrowserManager] = None
    _lock = threading.Lock()

    def __new__(cls) -> BrowserManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._history_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._installed_cache: Optional[dict[str, dict[str, Any]]] = None
        self._cache_time: float = 0.0
        self._history: list[dict[str, Any]] = self._load_history()
        self._initialized = True

    # ─────────────────────────────────────────────────────────────────────────
    # History Management
    # ─────────────────────────────────────────────────────────────────────────
    def _load_history(self) -> list[dict[str, Any]]:
        """Load browser visit history from JSON."""
        try:
            if _HISTORY_FILE.exists():
                data = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
        except Exception as e:
            print(f"[BrowserManager] Failed to load history: {e}")
        return []

    def _save_history(self) -> None:
        """Persist browser visit history."""
        try:
            _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
            _HISTORY_FILE.write_text(
                json.dumps(self._history[-50:], indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[BrowserManager] Failed to save history: {e}")

    def record_visit(self, url: str, browser: str, title: str = "") -> None:
        """Record a visited website into persistent history."""
        if not url or url in ("about:blank", ""):
            return
        with self._history_lock:
            entry = {
                "url": url,
                "browser": browser,
                "title": title or url,
                "timestamp": datetime.now().isoformat()
            }
            # Avoid duplicate immediate consecutive entries
            if self._history and self._history[-1].get("url") == url:
                self._history[-1] = entry
            else:
                self._history.append(entry)
            self._save_history()

    def get_last_visited(self) -> Optional[dict[str, Any]]:
        """Get the most recently visited website details."""
        with self._history_lock:
            if self._history:
                return dict(self._history[-1])
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # URL and Name Normalization
    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    def normalize_browser_name(name: Optional[str]) -> str:
        """Map spoken variations to canonical key, e.g. 'Google Chrome' -> 'chrome'."""
        if not name:
            return "default"
        clean = name.strip().lower()
        # Clean phrases like "my default browser", "in edge", "on chrome"
        clean = re.sub(r"^(in|on|using|with)\s+", "", clean).strip()
        return BROWSER_ALIASES.get(clean, clean)

    @staticmethod
    def resolve_url(target: str) -> str:
        """
        Convert website shorthand or domain into a full valid URL.
        e.g.:
          'gmail' -> 'https://mail.google.com'
          'linkedin' -> 'https://www.linkedin.com'
          'github.com/my-repo' -> 'https://github.com/my-repo'
        """
        if not target or not target.strip():
            return "about:blank"
        target = target.strip()

        # Check website shortcuts first
        lower = target.lower()
        if lower in WEBSITE_SHORTCUTS:
            return WEBSITE_SHORTCUTS[lower]

        # If already full scheme
        if "://" in target:
            return target

        # Handle domains like "github.com" or "mail.google.com/foo"
        if "." in target and not target.endswith("."):
            return "https://" + target

        # Fallback to .com domain
        return f"https://{target}.com"

    # ─────────────────────────────────────────────────────────────────────────
    # Detection of Installed Browsers
    # ─────────────────────────────────────────────────────────────────────────
    def detect_default_browser(self) -> str:
        """Identify system default browser key via OS registry or association."""
        if _OS == "Windows":
            try:
                import winreg
                k = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice"
                )
                prog_id, _ = winreg.QueryValueEx(k, "ProgId")
                winreg.CloseKey(k)
                prog_lower = prog_id.lower()
                for key, meta in BROWSER_METADATA.items():
                    for kw in meta["default_keywords"]:
                        if kw in prog_lower:
                            return key
            except Exception:
                pass
            return "edge"  # Standard default on modern Windows

        elif _OS == "Darwin":
            try:
                out = subprocess.run(
                    ["defaults", "read",
                     "com.apple.LaunchServices/com.apple.launchservices.secure",
                     "LSHandlers"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
                ).stdout.lower()
                for key in ("chrome", "edge", "firefox", "brave", "safari", "opera", "vivaldi"):
                    if key in out:
                        return key
            except Exception:
                pass
            return "safari"

        else:
            try:
                out = subprocess.run(
                    ["xdg-settings", "get", "default-web-browser"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
                ).stdout.lower()
                for key in ("chrome", "edge", "firefox", "brave", "opera", "vivaldi"):
                    if key in out:
                        return key
            except Exception:
                pass
            return "firefox"

    def get_installed_browsers(self, force_refresh: bool = False) -> dict[str, dict[str, Any]]:
        """
        Dynamically scans the system and returns all detected installed browsers.
        Result schema:
          {
            "chrome": {
              "key": "chrome",
              "display_name": "Google Chrome",
              "exe_path": "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
              "is_default": False
            },
            ...
          }
        """
        with self._cache_lock:
            now = time.monotonic()
            if not force_refresh and self._installed_cache is not None and (now - self._cache_time) < 60:
                return self._installed_cache

            default_key = self.detect_default_browser()
            detected: dict[str, dict[str, Any]] = {}

            if _OS == "Windows":
                detected = self._scan_windows(default_key)
            elif _OS == "Darwin":
                detected = self._scan_macos(default_key)
            else:
                detected = self._scan_linux(default_key)

            # Ensure default browser has is_default = True
            if default_key in detected:
                detected[default_key]["is_default"] = True
            elif detected:
                # If detected list doesn't include designated default, pick first
                first_key = next(iter(detected.keys()))
                detected[first_key]["is_default"] = True

            self._installed_cache = detected
            self._cache_time = now
            return detected

    def _scan_windows(self, default_key: str) -> dict[str, dict[str, Any]]:
        """Windows browser discovery via Registry (App Paths, StartMenuInternet) and disk paths."""
        results: dict[str, dict[str, Any]] = {}
        import winreg

        # 1. Registry App Paths
        for key, meta in BROWSER_METADATA.items():
            exe_path = None
            for app_exe in meta.get("win_app_paths", []):
                for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                    try:
                        k = winreg.OpenKey(
                            hive,
                            rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{app_exe}"
                        )
                        val, _ = winreg.QueryValueEx(k, "")
                        winreg.CloseKey(k)
                        cleaned = val.strip().strip('"')
                        if cleaned and Path(cleaned).exists():
                            exe_path = cleaned
                            break
                    except Exception:
                        continue
                if exe_path:
                    break

            if exe_path:
                results[key] = {
                    "key": key,
                    "display_name": meta["display_name"],
                    "exe_path": exe_path,
                    "is_default": (key == default_key),
                }

        # 2. Registry StartMenuInternet
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                root_k = winreg.OpenKey(hive, r"SOFTWARE\Clients\StartMenuInternet")
                idx = 0
                while True:
                    try:
                        sub_name = winreg.EnumKey(root_k, idx)
                        idx += 1
                        cmd_k = winreg.OpenKey(root_k, rf"{sub_name}\shell\open\command")
                        val, _ = winreg.QueryValueEx(cmd_k, "")
                        winreg.CloseKey(cmd_k)
                        cleaned = val.strip().strip('"').split('"')[0].split(" --")[0].strip()
                        if cleaned and Path(cleaned).exists():
                            # Determine which browser this corresponds to
                            sub_lower = sub_name.lower()
                            matched_key = None
                            for key, meta in BROWSER_METADATA.items():
                                for sm in meta.get("win_start_menu", []):
                                    if sm.lower() in sub_lower or sm.lower() in cleaned.lower():
                                        matched_key = key
                                        break
                                if matched_key:
                                    break
                            if not matched_key:
                                for key in BROWSER_METADATA:
                                    if key in sub_lower or key in cleaned.lower():
                                        matched_key = key
                                        break
                            if matched_key and matched_key not in results:
                                results[matched_key] = {
                                    "key": matched_key,
                                    "display_name": BROWSER_METADATA[matched_key]["display_name"],
                                    "exe_path": cleaned,
                                    "is_default": (matched_key == default_key),
                                }
                    except OSError:
                        break
                winreg.CloseKey(root_k)
            except Exception:
                pass

        # 3. Common Program Files & LocalAppData fallback checks
        prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        prog_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local_app = os.environ.get("LocalAppData", "")
        roam_app = os.environ.get("AppData", "")

        disk_candidates = {
            "chrome": [
                Path(prog_files) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(prog_x86) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(local_app) / "Google" / "Chrome" / "Application" / "chrome.exe",
            ],
            "edge": [
                Path(prog_files) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                Path(prog_x86) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            ],
            "brave": [
                Path(prog_files) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
                Path(prog_x86) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
                Path(local_app) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            ],
            "firefox": [
                Path(prog_files) / "Mozilla Firefox" / "firefox.exe",
                Path(prog_x86) / "Mozilla Firefox" / "firefox.exe",
            ],
            "opera": [
                Path(local_app) / "Programs" / "Opera" / "opera.exe",
                Path(prog_files) / "Opera" / "opera.exe",
                Path(prog_x86) / "Opera" / "opera.exe",
            ],
            "operagx": [
                Path(local_app) / "Programs" / "Opera GX" / "opera.exe",
                Path(prog_files) / "Opera GX" / "opera.exe",
                Path(prog_x86) / "Opera GX" / "opera.exe",
            ],
            "vivaldi": [
                Path(local_app) / "Vivaldi" / "Application" / "vivaldi.exe",
                Path(prog_files) / "Vivaldi" / "Application" / "vivaldi.exe",
            ],
        }

        for key, paths in disk_candidates.items():
            if key not in results:
                for p in paths:
                    if p.exists():
                        results[key] = {
                            "key": key,
                            "display_name": BROWSER_METADATA[key]["display_name"],
                            "exe_path": str(p),
                            "is_default": (key == default_key),
                        }
                        break

        # 4. PATH lookup fallback
        for key, meta in BROWSER_METADATA.items():
            if key not in results:
                for b in meta.get("win_exes", []):
                    found = shutil.which(b)
                    if found and Path(found).exists():
                        results[key] = {
                            "key": key,
                            "display_name": meta["display_name"],
                            "exe_path": found,
                            "is_default": (key == default_key),
                        }
                        break

        return results

    def _scan_macos(self, default_key: str) -> dict[str, dict[str, Any]]:
        """macOS browser discovery via /Applications and system bins."""
        results: dict[str, dict[str, Any]] = {}
        for key, meta in BROWSER_METADATA.items():
            for app_name in meta.get("mac_apps", []):
                app_path = Path("/Applications") / app_name
                if app_path.exists():
                    results[key] = {
                        "key": key,
                        "display_name": meta["display_name"],
                        "exe_path": str(app_path),
                        "is_default": (key == default_key),
                    }
                    break
        return results

    def _scan_linux(self, default_key: str) -> dict[str, dict[str, Any]]:
        """Linux browser discovery via PATH lookup."""
        results: dict[str, dict[str, Any]] = {}
        for key, meta in BROWSER_METADATA.items():
            for b in meta.get("linux_bins", []):
                found = shutil.which(b)
                if found and Path(found).exists():
                    results[key] = {
                        "key": key,
                        "display_name": meta["display_name"],
                        "exe_path": found,
                        "is_default": (key == default_key),
                    }
                    break
        return results

    # ─────────────────────────────────────────────────────────────────────────
    # Resolution and Launching
    # ─────────────────────────────────────────────────────────────────────────
    def resolve_target_browser(
        self, requested_name: Optional[str] = None
    ) -> Tuple[Optional[dict[str, Any]], Optional[dict[str, Any]], bool]:
        """
        Resolves the browser to launch.
        Returns:
          (selected_browser_info, default_browser_info, is_fallback)
        """
        installed = self.get_installed_browsers()
        default_key = self.detect_default_browser()
        default_info = installed.get(default_key)
        if not default_info and installed:
            default_info = next(iter(installed.values()))

        normalized = self.normalize_browser_name(requested_name)
        if normalized == "default":
            return (default_info, default_info, False)

        if normalized in installed:
            return (installed[normalized], default_info, False)

        # The requested browser is not installed
        return (None, default_info, True)

    def open_website(
        self,
        url: str = "",
        browser_name: Optional[str] = None,
        fallback_to_default: bool = True,
    ) -> dict[str, Any]:
        """
        Natively opens a website in the specified browser preserving the
        user's real profile, logged-in sessions, cookies, extensions, and tabs.
        Does NOT launch an isolated sandbox or headless automation instance.
        """
        resolved_url = self.resolve_url(url) if url and url.strip() else ""
        selected, default_info, is_fallback = self.resolve_target_browser(browser_name)

        req_norm = self.normalize_browser_name(browser_name)
        req_display = BROWSER_METADATA.get(req_norm, {}).get("display_name", browser_name or "Default")

        # Case 1: Requested browser is NOT installed
        if selected is None:
            if not fallback_to_default or default_info is None:
                avail_names = [b["display_name"] for b in self.get_installed_browsers().values()]
                avail_str = ", ".join(avail_names) if avail_names else "none"
                return {
                    "success": False,
                    "verified": False,
                    "operation": "open",
                    "browser": req_norm,
                    "requested": req_display,
                    "message": (
                        f"{req_display} is not installed on this PC. "
                        f"Installed browsers: {avail_str}."
                    ),
                }

            # Fallback to default browser
            selected = default_info
            def_name = default_info["display_name"]
            notice = f"{req_display} is not installed. Opened in your default browser ({def_name}) instead."
        else:
            notice = f"Opened in {selected['display_name']}."

        target_browser_key = selected["key"]
        target_display = selected["display_name"]
        exe = selected.get("exe_path")

        # Execute Native Launch
        try:
            if _OS == "Windows":
                if exe and Path(exe).exists():
                    args = [exe, resolved_url] if resolved_url else [exe]
                    subprocess.Popen(
                        args,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                elif resolved_url:
                    os.startfile(resolved_url)
                else:
                    return {
                        "success": False,
                        "verified": False,
                        "operation": "open",
                        "browser": target_browser_key,
                        "message": f"Could not find valid launch path for {target_display}."
                    }

            elif _OS == "Darwin":
                if exe:
                    cmd = ["open", "-a", exe] + ([resolved_url] if resolved_url else [])
                    subprocess.run(cmd, check=True, timeout=10)
                elif resolved_url:
                    subprocess.run(["open", resolved_url], check=True, timeout=10)

            else:  # Linux
                if exe:
                    args = [exe, resolved_url] if resolved_url else [exe]
                    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif resolved_url:
                    subprocess.Popen(["xdg-open", resolved_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Record visit in history
            if resolved_url:
                self.record_visit(resolved_url, target_browser_key)

            msg = f"{notice} (URL: {resolved_url})" if resolved_url else notice
            return {
                "success": True,
                "verified": True,
                "operation": "open",
                "browser": target_browser_key,
                "browser_display": target_display,
                "url": resolved_url,
                "reused_session": True,
                "fallback_used": is_fallback,
                "message": msg,
            }

        except Exception as e:
            print(f"[BrowserManager] Failed native launch for {target_display}: {e}")
            return {
                "success": False,
                "verified": False,
                "operation": "open",
                "browser": target_browser_key,
                "url": resolved_url,
                "message": f"Failed to launch {target_display}: {e}",
            }

    def open_last_visited(self, browser_name: Optional[str] = None) -> dict[str, Any]:
        """Reopen the most recently visited website."""
        last = self.get_last_visited()
        if not last or not last.get("url"):
            return {
                "success": False,
                "verified": False,
                "operation": "open_last",
                "message": "No previously visited websites recorded in memory.",
            }

        url = last["url"]
        target_browser = browser_name or last.get("browser")
        res = self.open_website(url=url, browser_name=target_browser)
        res["operation"] = "open_last"
        res["last_visited_url"] = url
        res["message"] = f"Reopened your last visited website: {url}"
        return res

    def search_query(
        self,
        query: str,
        browser_name: Optional[str] = None,
        engine: str = "google",
    ) -> dict[str, Any]:
        """Perform a web search in the user's real browser using their active session."""
        query = (query or "").strip()
        if not query:
            return {
                "success": False,
                "verified": False,
                "operation": "search",
                "message": "Search query cannot be empty.",
            }

        base = SEARCH_ENGINES.get(engine.lower(), SEARCH_ENGINES["google"])
        search_url = base + query.replace(" ", "+")
        res = self.open_website(url=search_url, browser_name=browser_name)
        res["operation"] = "search"
        res["query"] = query
        res["engine"] = engine
        res["message"] = f"Searched for '{query}' on {engine.capitalize()} in {res.get('browser_display', 'browser')}."
        return res

    def list_installed_summary(self) -> dict[str, Any]:
        """Provides a user-friendly and structured summary of all installed browsers."""
        installed = self.get_installed_browsers(force_refresh=True)
        default_key = self.detect_default_browser()

        items = []
        for key, data in installed.items():
            is_def = (key == default_key) or data.get("is_default", False)
            items.append({
                "key": key,
                "name": data["display_name"],
                "path": data.get("exe_path", ""),
                "is_default": is_def
            })

        lines = ["Installed Browsers on this PC:"]
        for it in items:
            def_mark = " (Default)" if it["is_default"] else ""
            lines.append(f"  * {it['name']}{def_mark}")

        return {
            "success": True,
            "verified": True,
            "operation": "list_browsers",
            "total_count": len(items),
            "browsers": items,
            "default_browser": default_key,
            "summary_text": "\n".join(lines),
            "message": "\n".join(lines),
        }


# Singleton accessor
browser_mgr = BrowserManager()
