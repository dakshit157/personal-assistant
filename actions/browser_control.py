
from __future__ import annotations

import asyncio
import concurrent.futures
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import threading
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from core import appidentity, outcome
from core.browser_manager import browser_mgr, BrowserManager

# Importing playwright cost 198 ms at every launch, paid by action discovery
# whether or not a browser was ever opened. It is the second-largest import in
# the project after pyautogui, and together the two were 78% of all module
# import time on the boot path.
#
# WHY THIS STILL RAISES WHEN PLAYWRIGHT IS MISSING
#     The eager import had a second job nobody wrote down: when playwright was
#     absent this module failed to load, action_loader dropped it, and the model
#     was never offered a browser tool it could not serve. Deferring the import
#     without keeping that would declare `browser_control` on a machine that
#     cannot run it -- the model would call it, get an exception, and describe a
#     page it never opened. Exactly the failure mode this project spent Mark LVI
#     removing from local engines.
#
#     So the check stays at module scope and still stops the module loading; it
#     just asks find_spec instead of executing the package. 1 ms instead of 198,
#     same outcome, and a sentence that says what to install.
if importlib.util.find_spec("playwright") is None:      # pragma: no cover
    raise ImportError(
        "browser_control needs playwright, which is not installed. "
        "Run: pip install playwright  &&  playwright install chromium"
    )

# Annotations only -- `from __future__ import annotations` above makes every one
# of them a string, so these names are never looked up at runtime and cost
# nothing outside a type checker.
if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page, Playwright

# WHY THIS FILE DOES NOT USE core/lazyimport.py's LazyModule LIKE THE OTHERS
#     Every other deferral in this project stands a proxy in for a whole module,
#     because the call sites say `pyautogui.press(...)` and a proxy answers that
#     the same way the module would. What this file needs are two SYMBOLS out of
#     a module: a factory function, and an exception class used in `except`.
#
#     `except` will not take a proxy. It requires a real class inheriting from
#     BaseException, checked by the interpreter at the moment the exception is
#     raised, and a LazyModule there raises TypeError instead of catching
#     anything -- the original error then disappears underneath a complaint about
#     the except clause. So these two are bound as real globals instead.
#
# PlaywrightTimeout starts as a private class that is never raised, so an
# `except PlaywrightTimeout:` somehow reached before a session exists catches
# nothing rather than failing that same way.
class _PlaywrightNotLoaded(Exception):
    """Placeholder exception -- declared so `except` clauses stay valid, and
    deliberately never raised anywhere."""


async_playwright = None
PlaywrightTimeout: type[BaseException] = _PlaywrightNotLoaded


def _load_playwright() -> None:
    """Import playwright and bind the two runtime symbols. Idempotent."""
    global async_playwright, PlaywrightTimeout
    if async_playwright is not None:
        return
    from playwright.async_api import (          # noqa: PLC0415 -- deliberate
        async_playwright as _ap,
        TimeoutError as _timeout,
    )
    async_playwright = _ap
    PlaywrightTimeout = _timeout


_OS = platform.system()   # "Windows" | "Darwin" | "Linux"

def _normalize_url(url: str) -> str:
    return browser_mgr.resolve_url(url)
def _user_agent() -> str:
    if _OS == "Windows":
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    if _OS == "Darwin":
        return (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    return (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )


def _real_profile_dir(browser: str) -> str:
    home  = Path.home()
    local = os.environ.get("LOCALAPPDATA", "")
    roam  = os.environ.get("APPDATA", "")

    candidates: list[Path] = []

    if _OS == "Windows":
        m = {
            "chrome":   [Path(local) / "Google"          / "Chrome"          / "User Data"],
            "edge":     [Path(local) / "Microsoft"        / "Edge"            / "User Data"],
            "brave":    [Path(local) / "BraveSoftware"    / "Brave-Browser"   / "User Data"],
            "vivaldi":  [Path(local) / "Vivaldi"          / "User Data"],
            "opera":    [Path(roam)  / "Opera Software"   / "Opera Stable",
                         Path(local) / "Opera Software"   / "Opera Stable"],
            "operagx":  [Path(roam)  / "Opera Software"   / "Opera GX Stable",
                         Path(local) / "Opera Software"   / "Opera GX Stable"],
        }
        candidates = m.get(browser, [])

    elif _OS == "Darwin":
        lib = home / "Library" / "Application Support"
        m = {
            "chrome":   [lib / "Google"             / "Chrome"],
            "edge":     [lib / "Microsoft Edge"],
            "brave":    [lib / "BraveSoftware"       / "Brave-Browser"],
            "vivaldi":  [lib / "Vivaldi"],
            "opera":    [lib / "com.operasoftware.Opera"],
            "operagx":  [lib / "com.operasoftware.OperaGX"],
        }
        candidates = m.get(browser, [])

    elif _OS == "Linux":
        cfg = home / ".config"
        m = {
            "chrome":   [cfg / "google-chrome", cfg / "chromium"],
            "edge":     [cfg / "microsoft-edge"],
            "brave":    [cfg / "BraveSoftware" / "Brave-Browser"],
            "vivaldi":  [cfg / "vivaldi"],
            "opera":    [cfg / "opera"],
            "operagx":  [cfg / "opera-gx"],
        }
        candidates = m.get(browser, [])

    for p in candidates:
        if p.exists():
            print(f"[Browser] [OK] Real profile found for {browser}: {p}")
            return str(p)

    fallback = home / ".jarvis_profiles" / browser
    fallback.mkdir(parents=True, exist_ok=True)
    print(f"[Browser] [WARN]  Real profile not found for {browser}, using: {fallback}")
    return str(fallback)

def _firefox_profile_dir() -> Optional[str]:
    home = Path.home()

    if _OS == "Windows":
        base = Path(os.environ.get("APPDATA", "")) / "Mozilla" / "Firefox"
    elif _OS == "Darwin":
        base = home / "Library" / "Application Support" / "Firefox"
    else:
        base = home / ".mozilla" / "firefox"

    ini = base / "profiles.ini"
    if not ini.exists():
        return None

    current: dict[str, str] = {}
    default_path: Optional[str] = None

    for line in ini.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("["):
            p = current.get("Path", "")
            if p and current.get("Default") == "1":
                is_rel = current.get("IsRelative", "1") == "1"
                default_path = str(base / p) if is_rel else p
            current = {}
        elif "=" in line:
            k, _, v = line.partition("=")
            current[k.strip()] = v.strip()

    p = current.get("Path", "")
    if p and current.get("Default") == "1":
        is_rel = current.get("IsRelative", "1") == "1"
        default_path = str(base / p) if is_rel else p

    if default_path and Path(default_path).exists():
        print(f"[Browser] Firefox real profile: {default_path}")
        return default_path
    return None

def _find_opera_windows() -> Optional[str]:
    local  = os.environ.get("LOCALAPPDATA", "")
    prog   = os.environ.get("PROGRAMFILES", "")
    prog86 = os.environ.get("PROGRAMFILES(X86)", "")

    candidates = [
        Path(local)  / "Programs" / "Opera"    / "opera.exe",
        Path(local)  / "Programs" / "Opera GX" / "opera.exe",
        Path(prog)   / "Opera"    / "opera.exe",
        Path(prog86) / "Opera"    / "opera.exe",
    ]
    for p in candidates:
        if p.exists():
            print(f"[Browser] Opera found at: {p}")
            return str(p)

    try:
        import winreg
        keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\opera.exe",
            r"SOFTWARE\Clients\StartMenuInternet\OperaStable\shell\open\command",
            r"SOFTWARE\Clients\StartMenuInternet\OperaGXStable\shell\open\command",
            r"SOFTWARE\Clients\StartMenuInternet\opera\shell\open\command",
        ]
        for key_path in keys:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    k   = winreg.OpenKey(hive, key_path)
                    val = winreg.QueryValue(k, None)
                    winreg.CloseKey(k)
                    exe = val.strip().strip('"').split('"')[0].split(" --")[0].strip()
                    if exe and Path(exe).exists():
                        print(f"[Browser] Opera found via registry: {exe}")
                        return exe
                except Exception:
                    continue
    except Exception:
        pass

    return shutil.which("opera") or None

def _find_exe_windows(prog_name: str) -> Optional[str]:
    try:
        import winreg
        paths_to_try = [
            rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{prog_name}.exe",
            rf"SOFTWARE\Clients\StartMenuInternet\{prog_name}\shell\open\command",
        ]
        for key_path in paths_to_try:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    k   = winreg.OpenKey(hive, key_path)
                    val = winreg.QueryValue(k, None)
                    winreg.CloseKey(k)
                    exe = val.strip().strip('"').split('"')[0].split(" --")[0].strip()
                    if exe and Path(exe).exists():
                        return exe
                except Exception:
                    continue
    except Exception:
        pass
    return None

_BROWSER_SPECS: dict[str, dict] = {
    "Windows": {
        "chrome":   {"engine": "chromium", "channel": "chrome",  "bins": []},
        "edge":     {"engine": "chromium", "channel": "msedge",  "bins": []},
        "firefox":  {"engine": "firefox",  "channel": None,      "bins": ["firefox.exe"]},
        "opera":    {"engine": "chromium", "channel": None,      "bins": ["opera.exe"],  "special": "opera_windows"},
        "operagx":  {"engine": "chromium", "channel": None,      "bins": [],             "special": "opera_windows"},
        "brave":    {"engine": "chromium", "channel": None,      "bins": ["brave.exe"]},
        "vivaldi":  {"engine": "chromium", "channel": None,      "bins": ["vivaldi.exe"]},
        "safari":   None,
    },
    "Darwin": {
        "chrome":   {"engine": "chromium", "channel": "chrome",  "bins": []},
        "edge":     {"engine": "chromium", "channel": "msedge",  "bins": ["microsoft-edge"]},
        "firefox":  {"engine": "firefox",  "channel": None,      "bins": ["firefox"]},
        "opera":    {"engine": "chromium", "channel": None,      "bins": ["opera"]},
        "operagx":  {"engine": "chromium", "channel": None,      "bins": ["opera"]},
        "brave":    {"engine": "chromium", "channel": None,      "bins": ["brave browser", "brave"]},
        "vivaldi":  {"engine": "chromium", "channel": None,      "bins": ["vivaldi"]},
        "safari":   {"engine": "webkit",   "channel": None,      "bins": []},
    },
    "Linux": {
        "chrome":   {"engine": "chromium", "channel": None,
                     "bins": ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"]},
        "edge":     {"engine": "chromium", "channel": None,
                     "bins": ["microsoft-edge", "microsoft-edge-stable"]},
        "firefox":  {"engine": "firefox",  "channel": None, "bins": ["firefox"]},
        "opera":    {"engine": "chromium", "channel": None, "bins": ["opera", "opera-stable"]},
        "operagx":  {"engine": "chromium", "channel": None, "bins": ["opera", "opera-stable"]},
        "brave":    {"engine": "chromium", "channel": None, "bins": ["brave-browser", "brave"]},
        "vivaldi":  {"engine": "chromium", "channel": None, "bins": ["vivaldi-stable", "vivaldi"]},
        "safari":   None,
    },
}

_ALIASES: dict[str, str] = {
    "google chrome":   "chrome",
    "google-chrome":   "chrome",
    "microsoft edge":  "edge",
    "ms edge":         "edge",
    "msedge":          "edge",
    "mozilla firefox": "firefox",
    "opera gx":        "operagx",
    "opera_gx":        "operagx",
}


def _resolve_browser(name: str) -> dict | None:
    name   = _ALIASES.get(name.lower().strip(), name.lower().strip())
    os_map = _BROWSER_SPECS.get(_OS, {})
    spec   = os_map.get(name)
    if spec is None:
        return None

    engine  = spec["engine"]
    channel = spec.get("channel")
    bins    = spec.get("bins", [])
    exe     = None

    if spec.get("special") == "opera_windows":
        exe = _find_opera_windows()
        if not exe:
            print(f"[Browser] [WARN]  Opera executable not found on Windows.")
        return {"engine": engine, "exe": exe, "channel": channel}

    for b in bins:
        found = shutil.which(b)
        if found:
            exe = found
            break

    if not exe and _OS == "Darwin":
        app_names = {
            "chrome":  ["Google Chrome.app"],
            "edge":    ["Microsoft Edge.app"],
            "firefox": ["Firefox.app"],
            "opera":   ["Opera.app", "Opera GX.app"],
            "brave":   ["Brave Browser.app"],
            "vivaldi": ["Vivaldi.app"],
        }
        for app in app_names.get(name, []):
            app_dir = Path("/Applications") / app / "Contents" / "MacOS"
            if app_dir.exists():
                found_bins = list(app_dir.iterdir())
                if found_bins:
                    exe = str(found_bins[0])
                    break

    if not exe and _OS == "Windows" and not channel:
        exe = _find_exe_windows(name)
    if not exe:
        try:
            installed = browser_mgr.get_installed_browsers()
            if name in installed:
                exe = installed[name].get("exe_path")
        except Exception:
            pass

    return {"engine": engine, "exe": exe, "channel": channel}


def _detect_default_browser() -> str:
    try:
        return browser_mgr.detect_default_browser()
    except Exception:
        pass
    try:
        if _OS == "Windows":
            import winreg
            k = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations"
                r"\UrlAssociations\http\UserChoice",
            )
            prog_id = winreg.QueryValueEx(k, "ProgId")[0].lower()
            winreg.CloseKey(k)
            for kw in ("edge", "firefox", "opera", "brave", "vivaldi", "chrome"):
                if kw in prog_id:
                    return kw
        elif _OS == "Darwin":
            out = subprocess.run(
                ["defaults", "read",
                 "com.apple.LaunchServices/com.apple.launchservices.secure",
                 "LSHandlers"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
            ).stdout.lower()
            for kw in ("firefox", "opera", "brave", "vivaldi", "safari", "chrome", "edge"):
                if kw in out:
                    return kw
        elif _OS == "Linux":
            out = subprocess.run(
                ["xdg-settings", "get", "default-web-browser"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
            ).stdout.lower()
            for kw in ("firefox", "opera", "brave", "vivaldi", "chrome", "edge"):
                if kw in out:
                    return kw
    except Exception:
        pass
    return "chrome"


_SEARCH_ENGINES: dict[str, str] = {
    "google":     "https://www.google.com/search?q=",
    "bing":       "https://www.bing.com/search?q=",
    "duckduckgo": "https://duckduckgo.com/?q=",
    "yandex":     "https://yandex.com/search/?text=",
}

_MAC_APP_NAMES: dict[str, str] = {
    "chrome":  "Google Chrome",
    "edge":    "Microsoft Edge",
    "firefox": "Firefox",
    "opera":   "Opera",
    "operagx": "Opera GX",
    "brave":   "Brave Browser",
    "vivaldi": "Vivaldi",
    "safari":  "Safari",
}

# Windows registry lookup names for browsers whose spec has no explicit binary
_WIN_EXE_HINTS: dict[str, str] = {"chrome": "chrome", "edge": "msedge"}


def _open_native(url: str, browser_name: Optional[str]) -> str:
    """
    Opens the user's REAL browser normally -- with their own profile,
    logged-in accounts and extensions via BrowserManager.
    """
    res = browser_mgr.open_website(url=url, browser_name=browser_name)
    return json.dumps(res, indent=2)


class _BrowserSession:
    """
    A full session for one browser instance.
    All browsers open on the real profile via launch_persistent_context.
    """

    def __init__(self, browser_name: str):
        self.browser_name = browser_name
        self._spec        = _resolve_browser(browser_name)

        self._loop:    asyncio.AbstractEventLoop | None = None
        self._thread:  threading.Thread | None          = None
        self._ready    = threading.Event()

        self._pw:      Playwright     | None = None
        self._context: BrowserContext | None = None
        self._page:    Page           | None = None
        # "real" when the user's own browser profile was opened, "separate"
        # when their browser was already running and a private automation
        # profile had to be used instead. The difference is every sign-in they
        # have, so it is reported rather than only printed.
        self.profile_kind: str = ""

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name=f"BrowserThread-{self.browser_name}",
        )
        self._thread.start()
        self._ready.wait(timeout=20)

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._async_init())
        self._ready.set()
        self._loop.run_forever()

    async def _async_init(self):
        # The one door into a live session: nothing in this class reaches
        # async_playwright or PlaywrightTimeout without coming through here
        # first, so binding them at this point is enough for the whole file.
        _load_playwright()
        self._pw = await async_playwright().start()

    def run(self, coro, timeout: int = 60) -> str:
        if not self._loop:
            raise RuntimeError(f"Session for '{self.browser_name}' not started.")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def close(self):
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._async_close(), self._loop).result(10)

    async def _async_close(self):
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self._context = self._page = None

    async def _adopt_page(self) -> Page:
        """
        launch_persistent_context already opens a starting tab.
        Instead of opening a new blank tab (about:blank), it adopts that tab --
        so the user never sees an extra blank tab.
        """
        await asyncio.sleep(0.3)
        pages = self._context.pages
        return pages[0] if pages else await self._context.new_page()

    async def _launch(self):
        """
        Launches the browser with the real user profile.
        Does nothing if the context is already open.
        """
        if self._context is not None:
            return

        if self._spec is None:
            raise RuntimeError(
                f"'{self.browser_name}' bu platformda ({_OS}) desteklenmiyor."
            )

        engine_name = self._spec["engine"]
        exe         = self._spec["exe"]
        channel     = self._spec["channel"]
        engine_obj  = getattr(self._pw, engine_name)

        if engine_name == "firefox":
            profile = _firefox_profile_dir() or str(
                Path.home() / ".jarvis_profiles" / "firefox"
            )
            kwargs: dict = {
                "headless":    False,
                "slow_mo":     0,
                "viewport":    None,
                "no_viewport": True,
                "timeout":     25_000,
            }
            if exe:
                kwargs["executable_path"] = exe
            try:
                self._context = await engine_obj.launch_persistent_context(profile, **kwargs)
            except Exception as e:
                print(f"[Browser] Firefox real profile failed ({e}), using JARVIS profile")
                jarvis = str(Path.home() / ".jarvis_profiles" / "firefox_jarvis")
                Path(jarvis).mkdir(parents=True, exist_ok=True)
                self._context = await engine_obj.launch_persistent_context(jarvis, **kwargs)

            self._page = await self._adopt_page()
            print(f"[Browser] [OK] Firefox launched")
            return

        if engine_name == "webkit":
            safari_profile = str(Path.home() / ".jarvis_profiles" / "safari")
            Path(safari_profile).mkdir(parents=True, exist_ok=True)
            kwargs = {
                "headless":    False,
                "slow_mo":     0,
                "viewport":    None,
                "no_viewport": True,
                "timeout":     25_000,
            }
            self._context = await engine_obj.launch_persistent_context(safari_profile, **kwargs)
            self._page = await self._adopt_page()
            print(f"[Browser] [OK] Safari launched")
            return

        # Dedicated persistent JARVIS profile for automation.
        # This prevents collisions with any existing user Chrome instance (SingletonLock),
        # keeps cookies and accounts logged in across sessions, and avoids 25s timeouts.
        jarvis_profile = str(Path.home() / ".jarvis_profiles" / self.browser_name)
        Path(jarvis_profile).mkdir(parents=True, exist_ok=True)
        self.profile_kind = "persistent"

        # Check for and safely clear stale lock if no running automation process owns it
        lock_file = Path(jarvis_profile) / "SingletonLock"
        if lock_file.exists():
            try:
                lock_file.unlink(missing_ok=True)
            except Exception:
                pass

        kwargs = {
            "headless":    False,
            "slow_mo":     0,
            "viewport":    None,
            "no_viewport": True,
            "timeout":     25_000,
            "args": [
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--disable-default-apps",
                "--no-default-browser-check",
            ],
        }

        if exe:
            kwargs["executable_path"] = exe
        elif channel:
            kwargs["channel"] = channel

        label = (
            f"{self.browser_name}"
            + (f"/{channel}" if channel else "")
            + (f" @ {exe}" if exe else "")
        )

        try:
            self._context = await engine_obj.launch_persistent_context(jarvis_profile, **kwargs)
            self._page = await self._adopt_page()
            print(f"[Browser] [OK] Launched [{label}] with JARVIS persistent profile: {jarvis_profile}")
            return
        except Exception as e:
            print(f"[Browser] [WARN] First launch failed for {label}: {e}")

        # Fallback 1: Clear lockfile, wait 0.5s and retry
        await asyncio.sleep(0.5)
        if lock_file.exists():
            try:
                lock_file.unlink(missing_ok=True)
            except Exception:
                pass

        # Fallback 2: Launch via bundled Chromium (channel=None) to avoid Google Chrome mutex conflicts
        fallback_kwargs = dict(kwargs)
        fallback_kwargs.pop("channel", None)
        fallback_kwargs.pop("executable_path", None)
        try:
            self._context = await engine_obj.launch_persistent_context(jarvis_profile, **fallback_kwargs)
            self._page = await self._adopt_page()
            print(f"[Browser] [OK] Launched [{self.browser_name}] using Chromium engine fallback")
            return
        except Exception as e2:
            print(f"[Browser] [WARN] Chromium fallback failed for {self.browser_name}: {e2}")

        # Fallback 3: Fresh isolated sub-profile
        fresh_profile = str(Path.home() / ".jarvis_profiles" / f"{self.browser_name}_auto")
        Path(fresh_profile).mkdir(parents=True, exist_ok=True)
        try:
            self._context = await engine_obj.launch_persistent_context(fresh_profile, **fallback_kwargs)
            self._page = await self._adopt_page()
            print(f"[Browser] [OK] Launched [{self.browser_name}] with fresh auto profile")
        except Exception as e3:
            raise RuntimeError(f"Could not launch browser {self.browser_name}: {e3}") from e3


    async def _get_page(self) -> Page:
        await self._launch()
        # If somehow page got closed, open a fresh one
        if self._page is None or self._page.is_closed():
            self._page = await self._context.new_page()
            await asyncio.sleep(0.2)
        return self._page

    async def go_to(self, url: str) -> str:
        url      = _normalize_url(url)
        page     = await self._get_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(0.5)
        except PlaywrightTimeout:
            pass
        except Exception as e:
            print(f"[Browser] goto exception (non-fatal): {e}")

        curr_url = page.url
        title = ""
        try:
            title = await page.title()
        except Exception:
            pass

        # Detect Cloudflare challenge or login wall
        state = "ready"
        cf_detected = False
        login_detected = False
        try:
            content = await page.content()
            if any(term in content for term in ("cf-turnstile", "challenges.cloudflare.com", "Just a moment...", "Verify you are human")):
                cf_detected = True
                state = "cloudflare_challenge"
            elif any(k in curr_url.lower() for k in ("/login", "/signin", "/auth")):
                login_detected = True
                state = "login_required"
        except Exception:
            pass

        if curr_url and curr_url not in ("about:blank", "", None):
            msg = f"Navigated to {curr_url} ('{title}'). State: {state}."
            if cf_detected:
                msg += " Note: Cloudflare challenge detected on page. Manual verification may be required."
            elif login_detected:
                msg += " Note: Login or authentication required."

            res = {
                "success": True,
                "verified": True,
                "operation": "go_to",
                "browser": self.browser_name,
                "url": curr_url,
                "title": title,
                "state": state,
                "message": msg
            }
            return json.dumps(res, indent=2)

        res = {
            "success": False,
            "verified": False,
            "operation": "go_to",
            "browser": self.browser_name,
            "url": url,
            "message": "The page stayed blank - the address may be invalid or unreachable."
        }
        return json.dumps(res, indent=2)

    async def search(self, query: str, engine: str = "google") -> str:
        base = _SEARCH_ENGINES.get(engine.lower(), _SEARCH_ENGINES["google"])
        return await self.go_to(base + query.replace(" ", "+"))

    async def click(self, selector: str = None, text: str = None) -> str:
        page = await self._get_page()
        try:
            if text:
                await page.get_by_text(text, exact=False).first.click(timeout=8_000)
                return json.dumps({
                    "success": True, "verified": True, "operation": "click",
                    "text": text, "url": page.url, "message": f"Clicked text: '{text}'"
                }, indent=2)
            if selector:
                await page.click(selector, timeout=8_000)
                return json.dumps({
                    "success": True, "verified": True, "operation": "click",
                    "selector": selector, "url": page.url, "message": f"Clicked selector: {selector}"
                }, indent=2)
            return json.dumps({
                "success": False, "verified": False, "operation": "click",
                "message": "No element or selector was named to click"
            }, indent=2)
        except PlaywrightTimeout:
            return json.dumps({
                "success": False, "verified": False, "operation": "click",
                "selector": selector or text,
                "message": f"No element matching '{selector or text}' appeared on the page in time"
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "success": False, "verified": False, "operation": "click",
                "message": f"Click error: {e}"
            }, indent=2)

    async def type_text(self, selector: str = None, text: str = "",
                        clear_first: bool = True, press_enter: bool = False) -> str:
        page = await self._get_page()
        matched_sel = None
        target_el = None

        # 1. Explicit selector if given
        if selector:
            try:
                loc = page.locator(selector)
                if await loc.count() > 0:
                    matched_sel = selector
                    target_el = loc.first
            except Exception:
                pass

        # 2. AI composers (ChatGPT, Claude, Gemini, etc.)
        if target_el is None:
            ai_selectors = [
                "#prompt-textarea",
                "div[contenteditable='true']",
                "textarea[placeholder*='Message' i]",
                "textarea[placeholder*='Ask' i]",
                "textarea[data-id='root']",
                "div[data-placeholder*='Ask' i]",
                "[aria-label*='Message ChatGPT' i]",
                "[aria-label*='Prompt' i]",
                "textarea",
            ]
            for sel in ai_selectors:
                try:
                    loc = page.locator(sel)
                    cnt = await loc.count()
                    for i in range(cnt):
                        el = loc.nth(i)
                        if await el.is_visible():
                            matched_sel = sel
                            target_el = el
                            break
                    if target_el is not None:
                        break
                except Exception:
                    continue

        # 3. Active element if editable
        if target_el is None:
            try:
                is_editable = await page.evaluate(
                    "() => document.activeElement && (document.activeElement.tagName === 'INPUT' || "
                    "document.activeElement.tagName === 'TEXTAREA' || document.activeElement.isContentEditable)"
                )
                if is_editable:
                    loc = page.locator(":focus")
                    if await loc.count() > 0:
                        matched_sel = ":focus"
                        target_el = loc.first
            except Exception:
                pass

        # 4. First visible editable element
        if target_el is None:
            generic_selectors = [
                "textarea:visible",
                "input[type='text']:visible",
                "input[type='search']:visible",
                "input:not([type]):visible",
                "[contenteditable='true']:visible",
                "[role='textbox']:visible"
            ]
            for sel in generic_selectors:
                try:
                    loc = page.locator(sel)
                    if await loc.count() > 0:
                        matched_sel = sel
                        target_el = loc.first
                        break
                except Exception:
                    continue

        if target_el is None:
            return json.dumps({
                "success": False,
                "verified": False,
                "operation": "type",
                "browser": self.browser_name,
                "url": page.url,
                "typed_text": "",
                "message": f"Could not locate an input field or composer on {page.url}."
            }, indent=2)

        # Focus element
        try:
            await target_el.scroll_into_view_if_needed(timeout=3000)
            await target_el.click(timeout=3000)
            await asyncio.sleep(0.1)
        except Exception:
            pass

        # Clear if requested
        if clear_first:
            try:
                await target_el.clear(timeout=3000)
            except Exception:
                try:
                    await page.keyboard.press("Control+A")
                    await page.keyboard.press("Backspace")
                except Exception:
                    pass

        # Type text
        typed_ok = False
        try:
            await target_el.fill(text, timeout=4000)
            typed_ok = True
        except Exception:
            pass

        if not typed_ok:
            try:
                await target_el.type(text, delay=25, timeout=8000)
                typed_ok = True
            except Exception:
                pass

        if not typed_ok:
            try:
                await page.keyboard.type(text, delay=25)
                typed_ok = True
            except Exception as e:
                return json.dumps({
                    "success": False,
                    "verified": False,
                    "operation": "type",
                    "browser": self.browser_name,
                    "url": page.url,
                    "typed_text": "",
                    "message": f"Failed to type text into element ({matched_sel}): {e}"
                }, indent=2)

        # Post-typing verification: verify text in element or activeElement
        await asyncio.sleep(0.2)
        verified = False
        observed_val = ""
        try:
            observed_val = await target_el.evaluate(
                "el => el.value !== undefined ? el.value : (el.innerText || el.textContent || '')"
            )
            if text in observed_val or observed_val.strip() == text.strip():
                verified = True
        except Exception:
            pass

        if not verified:
            try:
                active_val = await page.evaluate(
                    "() => document.activeElement ? (document.activeElement.value || document.activeElement.innerText || document.activeElement.textContent || '') : ''"
                )
                if text in active_val or active_val.strip() == text.strip():
                    verified = True
                    observed_val = active_val
            except Exception:
                pass

        if press_enter:
            try:
                await page.keyboard.press("Enter")
            except Exception:
                pass

        return json.dumps({
            "success": True,
            "verified": verified,
            "operation": "type",
            "browser": self.browser_name,
            "url": page.url,
            "typed_text": text,
            "observed_text": observed_val[:200] if observed_val else text,
            "selector": matched_sel,
            "press_enter": press_enter,
            "message": f"Successfully typed '{text}' into '{matched_sel}' on {page.url} (verified={verified}). Browser remains open."
        }, indent=2)

    async def scroll(self, direction: str = "down", amount: int = 500) -> str:
        page = await self._get_page()
        try:
            y = amount if direction == "down" else -amount
            await page.mouse.wheel(0, y)
            return f"Scrolled {direction}."
        except Exception as e:
            return f"Scroll error: {e}"

    async def press(self, key: str) -> str:
        page = await self._get_page()
        try:
            await page.keyboard.press(key)
            return f"Pressed: {key}"
        except Exception as e:
            return f"Key error: {e}"

    async def get_text(self) -> str:
        page = await self._get_page()
        try:
            text = await page.inner_text("body")
            return text[:4_000]
        except Exception as e:
            return f"Could not get page text: {e}"

    async def get_url(self) -> str:
        page = await self._get_page()
        return page.url

    async def fill_form(self, fields: dict) -> str:
        page    = await self._get_page()
        results = []
        for selector, value in fields.items():
            try:
                el = page.locator(selector).first
                await el.clear()
                await el.type(str(value), delay=40)
                results.append(f"✓ {selector}")
            except Exception as e:
                results.append(f"✗ {selector}: {e}")
        return "Form filled: " + ", ".join(results)

    async def smart_click(self, description: str) -> str:
        page = await self._get_page()
        for role in ("button", "link", "searchbox", "textbox", "menuitem", "tab"):
            try:
                loc = page.get_by_role(role, name=description)
                if await loc.count() > 0:
                    await loc.first.click(timeout=5_000)
                    return f"Clicked ({role}): '{description}'"
            except Exception:
                pass
        for attempt in (
            lambda: page.get_by_text(description, exact=False).first.click(timeout=5_000),
            lambda: page.get_by_placeholder(description, exact=False).first.click(timeout=5_000),
            lambda: page.locator(
                f'[alt*="{description}" i],[title*="{description}" i],'
                f'[aria-label*="{description}" i]'
            ).first.click(timeout=5_000),
        ):
            try:
                await attempt()
                return f"Clicked: '{description}'"
            except Exception:
                pass
        return f"Could not find element: '{description}'"

    async def smart_type(self, description: str, text: str) -> str:
        page = await self._get_page()
        candidates = [
            ("placeholder", page.get_by_placeholder(description, exact=False)),
            ("label",       page.get_by_label(description, exact=False)),
            ("role",        page.get_by_role("textbox", name=description)),
            ("searchbox",   page.get_by_role("searchbox")),
            ("combobox",    page.get_by_role("combobox", name=description)),
        ]
        for method, loc in candidates:
            try:
                el = loc.first
                if await el.count() == 0:
                    continue
                await el.clear()
                await el.type(text, delay=50)
                return f"Typed into ({method}): '{description}'"
            except Exception:
                continue
        return f"Could not find input: '{description}'"

    async def new_tab(self, url: str = "") -> str:
        page = await self._get_page()
        ctx  = page.context
        new  = await ctx.new_page()
        self._page = new
        if url:
            return await self.go_to(url)
        return "New tab opened."

    async def close_tab(self) -> str:
        page = self._page
        if page and not page.is_closed():
            ctx   = page.context
            await page.close()
            pages = ctx.pages
            self._page = pages[-1] if pages else None
            return "Tab closed."
        return "No active tab to close."

    async def screenshot(self, path: str = None) -> str:
        page = await self._get_page()
        try:
            save_path = path or str(Path.home() / "Desktop" / "jarvis_screenshot.png")
            await page.screenshot(path=save_path, full_page=False)
            return f"Screenshot saved: {save_path}"
        except Exception as e:
            return f"Screenshot error: {e}"

    async def back(self) -> str:
        page = await self._get_page()
        try:
            await page.go_back(timeout=10_000)
            return f"Navigated back: {page.url}"
        except Exception as e:
            return f"Back error: {e}"

    async def forward(self) -> str:
        page = await self._get_page()
        try:
            await page.go_forward(timeout=10_000)
            return f"Navigated forward: {page.url}"
        except Exception as e:
            return f"Forward error: {e}"

    async def reload(self) -> str:
        page = await self._get_page()
        try:
            await page.reload(timeout=15_000)
            return f"Page reloaded: {page.url}"
        except Exception as e:
            return f"Reload error: {e}"

    async def close_browser(self) -> str:
        await self._async_close()
        return f"{self.browser_name} closed."

class _SessionRegistry:
    """Manages all active browser sessions."""

    def __init__(self):
        self._sessions:        dict[str, _BrowserSession] = {}
        self._active_browser:  str                        = ""
        self._lock             = threading.Lock()
        self._last_native_url: str                        = ""

    def has(self, browser_name: str | None = None) -> bool:
        """Is there an active automation session for this browser (or any)?"""
        with self._lock:
            if not browser_name:
                return bool(self._sessions)
            name = _ALIASES.get(browser_name.lower().strip(), browser_name.lower().strip())
            return name in self._sessions

    def note_native_url(self, url: str) -> None:
        self._last_native_url = url

    def pop_native_url(self) -> str:
        """Returns the last natively-opened URL once (consumed to avoid repeats)."""
        url, self._last_native_url = self._last_native_url, ""
        return url

    def _get_or_create(self, browser_name: str) -> _BrowserSession:
        with self._lock:
            if browser_name not in self._sessions:
                sess = _BrowserSession(browser_name)
                sess.start()
                self._sessions[browser_name] = sess
                print(f"[Registry] New session: {browser_name}")
            return self._sessions[browser_name]

    def get(self, browser_name: str | None = None) -> _BrowserSession:
        if not browser_name:
            browser_name = self._active_browser or _detect_default_browser()
        browser_name = _ALIASES.get(browser_name.lower().strip(), browser_name.lower().strip())
        sess = self._get_or_create(browser_name)
        self._active_browser = browser_name
        return sess

    def switch(self, browser_name: str) -> str:
        browser_name = _ALIASES.get(browser_name.lower().strip(), browser_name.lower().strip())
        self._get_or_create(browser_name)
        self._active_browser = browser_name
        return f"Active browser → {browser_name}"

    def close_one(self, browser_name: str) -> str:
        with self._lock:
            sess = self._sessions.pop(browser_name, None)
        if sess:
            sess.close()
            if self._active_browser == browser_name:
                self._active_browser = ""
            return f"{browser_name} closed."
        return f"No active session for: {browser_name}"

    def close_all(self) -> str:
        with self._lock:
            names    = list(self._sessions.keys())
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._active_browser = ""
        for s in sessions:
            try:
                s.close()
            except Exception:
                pass
        return "All browsers closed: " + (", ".join(names) if names else "none")

    def list_sessions(self) -> str:
        with self._lock:
            if not self._sessions:
                return "No active browser sessions."
            lines = []
            for name in self._sessions:
                marker = " ◀ active" if name == self._active_browser else ""
                lines.append(f"  • {name}{marker}")
            return "Open browsers:\n" + "\n".join(lines)


_registry = _SessionRegistry()

def browser_control(
    parameters:    dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params  = parameters or {}
    action  = params.get("action", "").lower().strip()
    browser = params.get("browser", "").lower().strip() or None
    mode    = params.get("mode", "").lower().strip()
    result  = "Unknown action."

    if action == "switch":
        target = browser or params.get("target", "").lower().strip()
        result = _registry.switch(target) if target else "Please specify a browser."
        _log(player, result)
        return result

    if action in ("list_browsers", "list_installed"):
        summary = browser_mgr.list_installed_summary()
        active = _registry.list_sessions()
        summary["active_sessions"] = active
        summary["summary_text"] += f"\n\nAutomation sessions: {active}"
        summary["message"] = summary["summary_text"]
        result = json.dumps(summary, indent=2)
        _log(player, result)
        return result

    if action in ("open", "open_browser", "open_native", "launch"):
        if mode == "automation":
            try:
                sess = _registry.get(browser)
                result = sess.run(sess.go_to(params.get("url", "")))
            except Exception as e:
                result = json.dumps({
                    "success": False, "verified": False, "operation": action,
                    "message": f"Could not start browser session: {e}"
                }, indent=2)
            _log(player, result)
            return result
        res = browser_mgr.open_website(
            url=params.get("url", ""),
            browser_name=browser,
            fallback_to_default=params.get("fallback_to_default", True)
        )
        result = json.dumps(res, indent=2)
        _log(player, result)
        return result

    if action in ("open_last", "reopen_last"):
        res = browser_mgr.open_last_visited(browser_name=browser)
        result = json.dumps(res, indent=2)
        _log(player, result)
        return result

    if action == "search":
        if mode == "automation":
            try:
                sess = _registry.get(browser)
                result = sess.run(sess.search(params.get("query", ""), params.get("engine", "google")))
            except Exception as e:
                result = json.dumps({
                    "success": False, "verified": False, "operation": action,
                    "message": f"Could not start browser session: {e}"
                }, indent=2)
            _log(player, result)
            return result
        res = browser_mgr.search_query(
            query=params.get("query", ""),
            browser_name=browser,
            engine=params.get("engine", "google")
        )
        result = json.dumps(res, indent=2)
        _log(player, result)
        return result

    if action == "close_all":
        result = _registry.close_all()
        _log(player, result)
        return result

    if action == "close":
        target = browser or _registry._active_browser
        result = _registry.close_one(target) if target else "No browser specified."
        _log(player, result)
        return result

    # Native bypass for go_to when explicitly requested
    if action == "go_to" and mode == "native":
        res = browser_mgr.open_website(
            url=params.get("url", ""),
            browser_name=browser,
            fallback_to_default=True
        )
        result = json.dumps(res, indent=2)
        _log(player, result)
        return result

    # Automation session for go_to, click, type, and DOM actions
    try:
        sess = _registry.get(browser)
    except Exception as e:
        result = json.dumps({
            "success": False, "verified": False, "operation": action,
            "message": f"Could not start browser session: {e}"
        }, indent=2)
        _log(player, result)
        return result

    try:
        if action == "go_to":
            url_target = params.get("url", "")
            result = sess.run(sess.go_to(url_target))
            try:
                browser_mgr.record_visit(url_target, browser or "chrome")
            except Exception:
                pass
        elif action == "new_tab":
            result = sess.run(sess.new_tab(params.get("url", "")))
        elif action == "click":
            result = sess.run(sess.click(params.get("selector"), params.get("text")))
        elif action == "type":
            result = sess.run(sess.type_text(
                selector=params.get("selector"),
                text=params.get("text", ""),
                clear_first=params.get("clear_first", True),
                press_enter=params.get("press_enter", False)
            ))
        elif action == "scroll":
            result = sess.run(sess.scroll(params.get("direction", "down"), int(params.get("amount", 500))))
        elif action == "fill_form":
            result = sess.run(sess.fill_form(params.get("fields", {})))
        elif action == "smart_click":
            result = sess.run(sess.smart_click(params.get("description", "")))
        elif action == "smart_type":
            result = sess.run(sess.smart_type(params.get("description", ""), params.get("text", "")))
        elif action == "get_text":
            result = sess.run(sess.get_text())
        elif action == "get_url":
            page_url = sess.run(sess.get_url())
            result = json.dumps({
                "success": True, "verified": True, "operation": "get_url",
                "url": page_url, "message": f"Current browser URL: {page_url}"
            }, indent=2)
        elif action == "press":
            result = sess.run(sess.press(params.get("key", "Enter")))
        elif action == "close_tab":
            result = sess.run(sess.close_tab())
        elif action == "screenshot":
            result = sess.run(sess.screenshot(params.get("path")))
        elif action == "back":
            result = sess.run(sess.back())
        elif action == "forward":
            result = sess.run(sess.forward())
        elif action == "reload":
            result = sess.run(sess.reload())
        else:
            result = json.dumps({
                "success": False, "verified": False, "operation": action,
                "message": f"Unknown browser action: '{action}'"
            }, indent=2)

    except concurrent.futures.TimeoutError:
        result = json.dumps({
            "success": False, "verified": False, "operation": action,
            "message": f"Browser action '{action}' timed out (60s)."
        }, indent=2)
    except Exception as e:
        result = json.dumps({
            "success": False, "verified": False, "operation": action,
            "message": f"Browser error ({action}): {e}"
        }, indent=2)

    _log(player, result)
    return result


def _log(player, text: str):
    short = str(text)[:80]
    print(f"[Browser] {short}")
    if player:
        print(f"[Browser] {short[:80]}")


TOOL = {
    "name": "browser_control",
    "description": (
        "Universal browser integration: controls and launches web browsers on this PC. "
        "Supports all installed browsers: Chrome, Edge, Brave, Firefox, Opera, Vivaldi, etc. "
        "FOR OPENING WEBSITES / NAVIGATION: "
        "Use action='open' with 'url' and optional 'browser'. This opens the website in the user's REAL browser window with their existing login sessions, cookies, extensions, and profiles preserved (no repeated logins). "
        "Examples: 'Open Gmail in Chrome', 'Open LinkedIn in Edge', 'Open YouTube in Firefox', 'Open GitHub in Brave', 'Open ChatGPT'. "
        "If the requested browser is not installed, it automatically uses the default browser and informs the user. "
        "FOR SEARCH: Use action='search' with 'query' and optional 'browser' and 'engine' (google, bing, duckduckgo). "
        "FOR REOPENING LAST VISITED SITE: Use action='open_last' ('Open the last website I visited'). "
        "FOR LISTING BROWSERS: Use action='list_browsers' to see installed browsers and default browser. "
        "FOR PROGRAMMATIC AUTOMATION: Use action='go_to', 'click', 'type', 'smart_click', 'get_text', 'screenshot' when multi-step DOM automation or reading page content is needed. "
        "Never call open_app for a browser before calling this tool."
    ),
    "brief": (
        "Controls web browsers: open URLs with existing logins, search, or automate pages."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "open | search | open_last | list_browsers | go_to | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | close | close_all"
            },
            "browser": {
                "type": "STRING",
                "description": "Target browser: chrome | edge | brave | firefox | opera | operagx | vivaldi | default. Omit to use default or active browser."
            },
            "url": {
                "type": "STRING",
                "description": "Website name or URL (e.g. gmail, linkedin, youtube, github, https://...)"
            },
            "query": {
                "type": "STRING",
                "description": "Search query for search action"
            },
            "engine": {
                "type": "STRING",
                "description": "Search engine: google | bing | duckduckgo (default: google)"
            },
            "mode": {
                "type": "STRING",
                "description": "native (opens real browser with login session, default for open) | automation (Playwright headless/automated session)"
            },
            "fallback_to_default": {
                "type": "BOOLEAN",
                "description": "Fallback to system default browser if requested browser is not installed (default: true)"
            },
            "selector": {
                "type": "STRING",
                "description": "CSS selector for click/type"
            },
            "text": {
                "type": "STRING",
                "description": "Text to click or type"
            },
            "description": {
                "type": "STRING",
                "description": "Element description for smart_click/smart_type"
            },
            "direction": {
                "type": "STRING",
                "description": "up | down for scroll"
            },
            "amount": {
                "type": "INTEGER",
                "description": "Scroll amount in pixels (default: 500)"
            },
            "key": {
                "type": "STRING",
                "description": "Key name for press action (e.g. Enter, Escape, F5)"
            },
            "path": {
                "type": "STRING",
                "description": "Save path for screenshot"
            },
            "clear_first": {
                "type": "BOOLEAN",
                "description": "Clear field before typing (default: true)"
            },
            "press_enter": {
                "type": "BOOLEAN",
                "description": "Press Enter after typing (default: false)"
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": browser_control,
}
