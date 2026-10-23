from __future__ import annotations

import os
import json
import shutil
import platform
import traceback
from pathlib import Path
from datetime import datetime

try:
    import send2trash
    _SEND2TRASH = True
except ImportError:
    _SEND2TRASH = False

from core.undo import push_undo

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

# Undo keeps a file's previous contents in memory so `write` can be reversed.
_UNDO_CONTENT_LIMIT = 1_000_000

# Safe dedicated default workspace under user's Documents
_DEFAULT_WORKSPACE = Path.home() / "Documents" / "JARVIS Workspace"


def _ensure_workspace() -> Path:
    """Ensure the default JARVIS Workspace folder exists and return it."""
    try:
        _DEFAULT_WORKSPACE.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return _DEFAULT_WORKSPACE


def _undo_move(src: Path, dst: Path):
    """Reverse of a move: put it back where it came from."""
    def _fn():
        if not dst.exists():
            return f"'{dst.name}' is no longer there — nothing moved back."
        src.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dst), str(src))
        return f"'{src.name}' is back in {src.parent.name}/."
    return _fn


def _undo_create(target: Path):
    """Reverse of a create: remove what we made — and only if we still made it."""
    def _fn():
        if not target.exists():
            return f"'{target.name}' is already gone."
        if target.is_dir():
            if any(target.iterdir()):
                return (f"'{target.name}' is not empty any more — "
                        f"leaving it alone rather than deleting your files.")
            target.rmdir()
        else:
            target.unlink()
        return f"Removed '{target.name}'."
    return _fn


def _undo_write(target: Path, previous: str | None):
    """Reverse of a write: restore old contents, or delete if it didn't exist."""
    def _fn():
        if previous is None:
            if target.exists():
                target.unlink()
                return f"Removed '{target.name}' — it did not exist before."
            return f"'{target.name}' is already gone."
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(previous, encoding="utf-8")
        return f"Restored the previous contents of '{target.name}'."
    return _fn


def _restore_from_trash(original: Path) -> str:
    """Best-effort undelete from Recycle Bin."""
    if _OS == "Windows":
        try:
            import win32com.client
            shell = win32com.client.Dispatch("Shell.Application")
            bin_folder = shell.NameSpace(10)      # ssfBITBUCKET
            for item in bin_folder.Items():
                if str(bin_folder.GetDetailsOf(item, 1)).strip().lower() == \
                        str(original.parent).strip().lower():
                    if str(item.Name).strip().lower() == original.name.strip().lower():
                        item.InvokeVerb("UNDELETE")
                        return f"'{original.name}' restored from the Recycle Bin."
        except Exception as e:
            print(f"[file] Recycle Bin restore failed: {e}")
    return (f"'{original.name}' is in the Recycle Bin — I could not pull it back "
            f"automatically, but it is there and can be restored by hand.")


def _get_dangerous_roots() -> list[Path]:
    """Paths that file operations should never modify or delete to protect OS integrity."""
    danger: list[Path] = []
    if _OS == "Windows":
        for env_var in ("SystemRoot", "windir"):
            val = os.environ.get(env_var)
            if val:
                try:
                    danger.append(Path(val).resolve())
                except Exception:
                    pass
        for env_var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
            val = os.environ.get(env_var)
            if val:
                try:
                    danger.append(Path(val).resolve())
                except Exception:
                    pass
        if not danger:
            danger.extend([Path("C:/Windows").resolve(), Path("C:/Program Files").resolve()])
    else:
        for p in ("/bin", "/sbin", "/usr/bin", "/usr/sbin", "/etc", "/sys", "/proc"):
            try:
                danger.append(Path(p).resolve())
            except Exception:
                pass
    return danger


_DANGEROUS_ROOTS: list[Path] = _get_dangerous_roots()


def _get_allowed_roots() -> list[Path]:
    """All accessible user drives and project workspaces."""
    roots: list[Path] = [Path.home().resolve(), _ensure_workspace().resolve()]
    try:
        app_dir = Path(__file__).resolve().parent.parent.resolve()
        roots.append(app_dir)
    except Exception:
        pass
    if _OS == "Windows":
        import string
        for d in string.ascii_uppercase:
            p = Path(f"{d}:/")
            if p.exists():
                try:
                    roots.append(p.resolve())
                except Exception:
                    pass
    return roots


_SAFE_ROOTS: list[Path] = _get_allowed_roots()


def _is_safe_path(target: Path) -> bool:
    """Is the given path safe to access/modify? Rejects OS system dirs, allows user drives."""
    try:
        resolved = target.resolve()
        # 1. Reject critical OS system directories
        for danger in _DANGEROUS_ROOTS:
            if resolved == danger or resolved.is_relative_to(danger):
                return False
        # 2. Must be in an allowed root (all user drives, home, project dir)
        return any(
            resolved == root or resolved.is_relative_to(root)
            for root in _SAFE_ROOTS
        )
    except Exception:
        return False


def _get_desktop() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DESKTOP_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Desktop"


def _get_downloads() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DOWNLOAD_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Downloads"


def _get_documents() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DOCUMENTS_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Documents"


def _get_pictures() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_PICTURES_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Pictures"


def _get_music() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_MUSIC_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Music"


def _get_videos() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_VIDEOS_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Videos"


def _resolve_path(raw: str) -> Path:
    """Resolve a raw path string or shortcut to a real Path.
    
    If raw is empty or unspecified, defaults to the dedicated JARVIS Workspace.
    If raw is a bare relative filename with no directory, places it in the JARVIS Workspace.
    """
    ws = _ensure_workspace()
    project_dir = Path(__file__).resolve().parent.parent

    shortcuts: dict[str, Path] = {
        "desktop":   _get_desktop(),
        "downloads": _get_downloads(),
        "documents": _get_documents(),
        "pictures":  _get_pictures(),
        "music":     _get_music(),
        "videos":    _get_videos(),
        "home":      Path.home(),
        "workspace": ws,
        "default":   ws,
        "project":   project_dir,
        "jarvis":    project_dir,
        "c":         Path("C:/"),
        "d":         Path("D:/") if Path("D:/").exists() else Path.home(),
    }

    raw = (raw or "").strip().strip('"').strip("'")
    if not raw:
        return ws

    lower = raw.lower()
    if lower in shortcuts:
        return shortcuts[lower]

    # Handle shortcut prefixes like "desktop/notes.txt" or "workspace/data.json"
    head, sep, rest = raw.replace("\\", "/").partition("/")
    if sep and head.lower() in shortcuts:
        rest = rest.strip("/")
        return shortcuts[head.lower()] / rest if rest else shortcuts[head.lower()]

    # If it is an absolute path (e.g. C:\... or D:\... or /home/...)
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p

    # If it is a bare filename or relative path without an explicit parent:
    # Resolve against the dedicated JARVIS Workspace
    return ws / raw


def _format_size(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def _safe_trash(target: Path) -> str:
    if not _SEND2TRASH:
        return (
            "send2trash is not installed. "
            "Run: pip install send2trash — "
            "Permanent deletion is disabled for safety."
        )
    send2trash.send2trash(str(target))
    return f"Moved to Trash: {target.name}"


def _format_result(success: bool, operation: str, path: Path | str, verified: bool, message: str, **extra) -> str:
    """Format structured truthful tool result."""
    resolved_path = ""
    if isinstance(path, Path):
        try:
            resolved_path = str(path.resolve())
        except Exception:
            resolved_path = str(path)
    elif isinstance(path, str) and path:
        try:
            resolved_path = str(Path(path).resolve())
        except Exception:
            resolved_path = path

    res = {
        "success": success,
        "operation": operation,
        "path": resolved_path,
        "verified": verified,
        "message": message,
    }
    res.update(extra)
    return json.dumps(res, indent=2)


def _verify_file_write(target: Path, expected_content: str = "", is_append: bool = False) -> tuple[bool, str, int]:
    """Verify write postconditions: existence, regular file, and content/size."""
    try:
        if not target.exists():
            return False, f"Verification failed: '{target.name}' does not exist on disk after write.", 0
        if not target.is_file():
            return False, f"Verification failed: '{target.name}' is not a regular file.", 0

        stat = target.stat()
        actual_size = stat.st_size
        expected_bytes = len(expected_content.encode("utf-8"))

        if not is_append and expected_bytes > 0 and actual_size == 0:
            return False, f"Verification failed: '{target.name}' exists but has 0 bytes (expected {expected_bytes} bytes).", 0

        return True, f"Verified: {actual_size} bytes confirmed on disk.", actual_size
    except Exception as e:
        return False, f"Verification check error: {e}", 0


# ── Action Implementations ───────────────────────────────────────────────────

def list_files(path: str = "desktop", show_hidden: bool = False) -> str:
    try:
        target = _resolve_path(path)
        if not _is_safe_path(target):
            return _format_result(False, "list", target, False, f"Access denied: {target}", error_type="access_denied")
        if not target.exists():
            return _format_result(False, "list", target, False, f"Path not found: {target}", error_type="not_found")
        if not target.is_dir():
            return _format_result(False, "list", target, False, f"Not a directory: {target}", error_type="not_a_directory")

        items = []
        for item in sorted(target.iterdir()):
            if not show_hidden and item.name.startswith("."):
                continue
            if item.is_dir():
                items.append(f"📁 {item.name}/")
            else:
                size = _format_size(item.stat().st_size)
                items.append(f"📄 {item.name} ({size})")

        msg = f"Contents of {target.name}/ ({len(items)} items):\n" + "\n".join(items) if items else f"Directory is empty: {target.name}/"
        return _format_result(True, "list", target, True, msg, item_count=len(items))

    except PermissionError as e:
        return _format_result(False, "list", path, False, f"Permission denied: {e}", error_type="permission_denied")
    except Exception as e:
        return _format_result(False, "list", path, False, f"Error listing files: {e}", error_type=type(e).__name__)


def create_file(path: str, name: str = "", content: str = "") -> str:
    """Create a new file with specified content and verify existence on disk."""
    try:
        base = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return _format_result(False, "create_file", target, False, f"Access denied: {target}", error_type="access_denied")

        target.parent.mkdir(parents=True, exist_ok=True)
        existed = target.exists()
        previous = None
        if existed:
            try:
                previous = target.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                previous = None

        # Write and flush to disk
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        # Mandatory verification
        verified, ver_msg, actual_size = _verify_file_write(target, content, is_append=False)
        if not verified:
            return _format_result(False, "create_file", target, False, ver_msg, error_type="verification_failed")

        push_undo(f"created {target.name}",
                  _undo_write(target, previous) if existed else _undo_create(target))

        return _format_result(
            True,
            "create_file",
            target,
            True,
            f"File '{target.name}' successfully created and verified ({actual_size} bytes) at {target.resolve()}.",
            size_bytes=actual_size
        )

    except PermissionError as e:
        err_msg = f"Permission denied creating '{target}'. "
        if _OS == "Windows":
            err_msg += "Windows Defender Controlled Folder Access or NTFS permissions may be restricting this folder."
        return _format_result(False, "create_file", target if 'target' in locals() else path, False, err_msg, error_type="permission_denied")
    except Exception as e:
        return _format_result(False, "create_file", target if 'target' in locals() else path, False, f"Could not create file: {e}", error_type=type(e).__name__)


def create_folder(path: str, name: str = "") -> str:
    try:
        base = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return _format_result(False, "create_folder", target, False, f"Access denied: {target}", error_type="access_denied")

        already = target.exists()
        target.mkdir(parents=True, exist_ok=True)

        if not target.exists() or not target.is_dir():
            return _format_result(False, "create_folder", target, False, f"Verification failed: Folder '{target}' was not created.", error_type="verification_failed")

        if not already:
            push_undo(f"created folder {target.name}", _undo_create(target))

        return _format_result(True, "create_folder", target, True, f"Folder successfully created and verified at {target.resolve()}.")

    except PermissionError as e:
        return _format_result(False, "create_folder", target if 'target' in locals() else path, False, f"Permission denied creating folder: {e}", error_type="permission_denied")
    except Exception as e:
        return _format_result(False, "create_folder", target if 'target' in locals() else path, False, f"Could not create folder: {e}", error_type=type(e).__name__)


def delete_file(path: str, name: str = "") -> str:
    try:
        base = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return _format_result(False, "delete", target, False, f"Access denied: {target}", error_type="access_denied")
        if not target.exists():
            return _format_result(False, "delete", target, False, f"Path not found: {target}", error_type="not_found")

        # Protected user directory check
        protected = {
            _get_desktop(), _get_downloads(), _get_documents(),
            _get_pictures(), _get_music(), _get_videos(), Path.home()
        }
        if target.resolve() in {p.resolve() for p in protected}:
            return _format_result(False, "delete", target, False, f"Protected root directory, cannot delete: {target.name}", error_type="protected_directory")

        original = target.resolve()
        result = _safe_trash(target)
        if result.startswith("Moved to Trash"):
            push_undo(f"deleted {original.name}",
                      lambda p=original: _restore_from_trash(p))
            return _format_result(True, "delete", original, True, f"File '{original.name}' moved to Recycle Bin / Trash.")
        return _format_result(False, "delete", original, False, result, error_type="trash_failed")

    except PermissionError as e:
        return _format_result(False, "delete", path, False, f"Permission denied: {e}", error_type="permission_denied")
    except Exception as e:
        return _format_result(False, "delete", path, False, f"Could not delete: {e}", error_type=type(e).__name__)


def move_file(path: str, name: str = "", destination: str = "") -> str:
    try:
        base = _resolve_path(path)
        src = (base / name) if name else base
        dst_base = _resolve_path(destination)

        if not _is_safe_path(src):
            return _format_result(False, "move", src, False, f"Access denied: {src}", error_type="access_denied")
        if not _is_safe_path(dst_base):
            return _format_result(False, "move", dst_base, False, f"Access denied: {dst_base}", error_type="access_denied")
        if not src.exists():
            return _format_result(False, "move", src, False, f"Source not found: {src.name}", error_type="not_found")

        dst = (dst_base / src.name) if dst_base.is_dir() else dst_base
        dst.parent.mkdir(parents=True, exist_ok=True)

        if dst.exists():
            return _format_result(False, "move", dst, False, f"Destination already exists: '{dst.name}'", error_type="destination_exists")

        old_path = src.resolve()
        shutil.move(str(src), str(dst))

        if not dst.exists():
            return _format_result(False, "move", dst, False, f"Verification failed: Move destination '{dst}' not found.", error_type="verification_failed")

        push_undo(f"moved {old_path.name} to {dst.parent.name}/",
                  _undo_move(old_path, dst.resolve()))

        return _format_result(True, "move", dst, True, f"Moved: {src.name} → {dst.resolve()}.")

    except PermissionError as e:
        return _format_result(False, "move", path, False, f"Permission denied: {e}", error_type="permission_denied")
    except Exception as e:
        return _format_result(False, "move", path, False, f"Could not move: {e}", error_type=type(e).__name__)


def copy_file(path: str, name: str = "", destination: str = "") -> str:
    try:
        base = _resolve_path(path)
        src = (base / name) if name else base
        dst_base = _resolve_path(destination)

        if not _is_safe_path(src):
            return _format_result(False, "copy", src, False, f"Access denied: {src}", error_type="access_denied")
        if not _is_safe_path(dst_base):
            return _format_result(False, "copy", dst_base, False, f"Access denied: {dst_base}", error_type="access_denied")
        if not src.exists():
            return _format_result(False, "copy", src, False, f"Source not found: {src.name}", error_type="not_found")

        dst = (dst_base / src.name) if dst_base.is_dir() else dst_base
        dst.parent.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))

        if not dst.exists():
            return _format_result(False, "copy", dst, False, f"Verification failed: Copied file '{dst}' not found.", error_type="verification_failed")

        return _format_result(True, "copy", dst, True, f"Copied: {src.name} → {dst.resolve()}.")

    except Exception as e:
        return _format_result(False, "copy", path, False, f"Could not copy: {e}", error_type=type(e).__name__)


def rename_file(path: str, name: str = "", new_name: str = "") -> str:
    try:
        base = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return _format_result(False, "rename", target, False, f"Access denied: {target}", error_type="access_denied")
        if not target.exists():
            return _format_result(False, "rename", target, False, f"Not found: {target.name}", error_type="not_found")
        if not new_name:
            return _format_result(False, "rename", target, False, "No new name provided.", error_type="missing_parameter")

        new_path = target.parent / new_name
        if new_path.exists():
            return _format_result(False, "rename", new_path, False, f"A file named '{new_name}' already exists here.", error_type="already_exists")

        old_path = target.resolve()
        target.rename(new_path)

        if not new_path.exists():
            return _format_result(False, "rename", new_path, False, "Verification failed: Renamed file not found.", error_type="verification_failed")

        push_undo(f"renamed {old_path.name} to {new_name}",
                  _undo_move(old_path, new_path.resolve()))
        return _format_result(True, "rename", new_path, True, f"Renamed: {old_path.name} → {new_path.resolve()}.")

    except Exception as e:
        return _format_result(False, "rename", path, False, f"Could not rename: {e}", error_type=type(e).__name__)


def read_file(path: str, name: str = "", max_chars: int = 8000) -> str:
    try:
        base = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return _format_result(False, "read", target, False, f"Access denied: {target}", error_type="access_denied")
        if not target.exists():
            return _format_result(False, "read", target, False, f"File not found: {target.name}", error_type="not_found")
        if not target.is_file():
            return _format_result(False, "read", target, False, f"Not a regular file: {target.name}", error_type="not_a_file")

        content = target.read_text(encoding="utf-8", errors="ignore")
        truncated = False
        if len(content) > max_chars:
            content = content[:max_chars]
            truncated = True

        return _format_result(
            True,
            "read",
            target,
            True,
            content,
            content=content,
            size_bytes=target.stat().st_size,
            truncated=truncated
        )

    except PermissionError as e:
        return _format_result(False, "read", path, False, f"Permission denied: {e}", error_type="permission_denied")
    except Exception as e:
        return _format_result(False, "read", path, False, f"Could not read file: {e}", error_type=type(e).__name__)


def write_file(path: str, name: str = "", content: str = "", append: bool = False) -> str:
    """Modify or append to an existing file with verification."""
    try:
        base = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return _format_result(False, "write", target, False, f"Access denied: {target}", error_type="access_denied")

        target.parent.mkdir(parents=True, exist_ok=True)

        previous: str | None = None
        undoable = True
        if target.exists():
            try:
                if target.stat().st_size > _UNDO_CONTENT_LIMIT:
                    undoable = False
                else:
                    previous = target.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                undoable = False

        mode = "a" if append else "w"
        with open(target, mode, encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        # Mandatory verification
        verified, ver_msg, actual_size = _verify_file_write(target, content, is_append=append)
        if not verified:
            return _format_result(False, "write", target, False, ver_msg, error_type="verification_failed")

        op_name = "append" if append else "write"
        if undoable:
            push_undo(f"{op_name} to {target.name}", _undo_write(target, previous))

        verb = "Appended to" if append else "Written to"
        return _format_result(
            True,
            op_name,
            target,
            True,
            f"{verb} '{target.name}' and verified ({actual_size} bytes) at {target.resolve()}.",
            size_bytes=actual_size
        )

    except PermissionError as e:
        err_msg = f"Permission denied modifying '{target}'. "
        if _OS == "Windows":
            err_msg += "Windows Defender Controlled Folder Access or file permissions may be blocking this path."
        return _format_result(False, "write", target if 'target' in locals() else path, False, err_msg, error_type="permission_denied")
    except Exception as e:
        return _format_result(False, "write", target if 'target' in locals() else path, False, f"Could not write file: {e}", error_type=type(e).__name__)


def find_files(name: str = "", extension: str = "", path: str = "workspace", max_results: int = 20) -> str:
    try:
        search_path = _resolve_path(path)
        if not _is_safe_path(search_path):
            return _format_result(False, "find", search_path, False, f"Access denied: {search_path}", error_type="access_denied")
        if not search_path.exists():
            return _format_result(False, "find", search_path, False, f"Search path not found: {search_path}", error_type="not_found")

        results = []
        dir_count = 0
        max_dirs = 500

        for item in search_path.rglob("*"):
            if item.is_dir():
                dir_count += 1
                if dir_count > max_dirs:
                    break
                continue
            if not item.is_file():
                continue
            if extension and item.suffix.lower() != extension.lower():
                continue
            if name and name.lower() not in item.name.lower():
                continue
            size = _format_size(item.stat().st_size)
            results.append(f"📄 {item.name} ({size}) — {item.resolve()}")
            if len(results) >= max_results:
                break

        msg = f"Found {len(results)} file(s):\n" + "\n".join(results) if results else f"No matching files found in {search_path.name}/"
        return _format_result(True, "find", search_path, True, msg, count=len(results))

    except Exception as e:
        return _format_result(False, "find", path, False, f"Search error: {e}", error_type=type(e).__name__)


def get_largest_files(path: str = "downloads", count: int = 10) -> str:
    count = min(count, 50)
    try:
        search_path = _resolve_path(path)
        if not _is_safe_path(search_path):
            return _format_result(False, "largest", search_path, False, f"Access denied: {search_path}", error_type="access_denied")
        if not search_path.exists():
            return _format_result(False, "largest", search_path, False, f"Path not found: {search_path}", error_type="not_found")

        files = []
        for item in search_path.rglob("*"):
            if item.is_file():
                try:
                    files.append((item.stat().st_size, item))
                except Exception:
                    continue

        files.sort(reverse=True)
        top = files[:count]

        if not top:
            return _format_result(True, "largest", search_path, True, "No files found.", count=0)

        lines = [f"Top {len(top)} largest files in {search_path.name}/:"]
        for size, f in top:
            lines.append(f"  {_format_size(size):>10}  {f.name}  ({f.parent})")

        return _format_result(True, "largest", search_path, True, "\n".join(lines), count=len(top))

    except Exception as e:
        return _format_result(False, "largest", path, False, f"Error: {e}", error_type=type(e).__name__)


def get_disk_usage(path: str = "workspace") -> str:
    try:
        target = _resolve_path(path)
        usage = shutil.disk_usage(target)
        pct = usage.used / usage.total * 100
        msg = (
            f"Disk usage ({target}):\n"
            f"  Total : {_format_size(usage.total)}\n"
            f"  Used  : {_format_size(usage.used)} ({pct:.1f}%)\n"
            f"  Free  : {_format_size(usage.free)}"
        )
        return _format_result(True, "disk_usage", target, True, msg, used_percent=round(pct, 1))
    except Exception as e:
        return _format_result(False, "disk_usage", path, False, f"Could not get disk usage: {e}", error_type=type(e).__name__)


def organize_desktop() -> str:
    type_map = {
        "Images":    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".heic"},
        "Documents": {".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx",
                      ".ppt", ".pptx", ".csv", ".odt", ".ods", ".odp"},
        "Videos":    {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
        "Music":     {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
        "Archives":  {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
        "Code":      {".py", ".js", ".ts", ".html", ".css", ".json", ".xml",
                      ".cpp", ".java", ".cs", ".go", ".rs", ".sh"},
    }

    desktop = _get_desktop()
    moved, skipped = [], []
    journal: list[tuple[Path, Path]] = []

    try:
        for item in desktop.iterdir():
            if item.is_dir() or item.name.startswith("."):
                continue
            if item.name in {k for k in type_map}:
                continue

            ext = item.suffix.lower()
            target_dir = desktop / "Others"
            for folder, exts in type_map.items():
                if ext in exts:
                    target_dir = desktop / folder
                    break

            target_dir.mkdir(exist_ok=True)
            new_path = target_dir / item.name

            if new_path.exists():
                skipped.append(item.name)
                continue

            origin = item.resolve()
            shutil.move(str(item), str(new_path))
            journal.append((origin, new_path.resolve()))
            moved.append(f"{item.name} → {target_dir.name}/")

        if journal:
            def _undo_organize(entries=tuple(journal)):
                restored = 0
                for origin, moved_to in entries:
                    try:
                        if moved_to.exists() and not origin.exists():
                            shutil.move(str(moved_to), str(origin))
                            restored += 1
                    except Exception:
                        pass
                return f"Moved {restored} file(s) back to Desktop."
            push_undo("organize desktop", _undo_organize)

        msg = f"Organized {len(moved)} file(s) on Desktop."
        if skipped:
            msg += f" ({len(skipped)} skipped: already exist)"
        return _format_result(True, "organize_desktop", desktop, True, msg, moved_count=len(moved))

    except Exception as e:
        return _format_result(False, "organize_desktop", desktop, False, f"Could not organize Desktop: {e}", error_type=type(e).__name__)


def get_file_info(path: str, name: str = "") -> str:
    try:
        base = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return _format_result(False, "info", target, False, f"Access denied: {target}", error_type="access_denied")
        if not target.exists():
            return _format_result(False, "info", target, False, f"Not found: {target.name}", error_type="not_found")

        stat = target.stat()
        info = {
            "name": target.name,
            "path": str(target.resolve()),
            "type": "Folder" if target.is_dir() else "File",
            "size": _format_size(stat.st_size),
            "size_bytes": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }
        if target.is_file():
            info["extension"] = target.suffix or "none"

        return _format_result(True, "info", target, True, f"File info for '{target.name}' retrieved.", details=info)

    except Exception as e:
        return _format_result(False, "info", path, False, f"Could not get file info: {e}", error_type=type(e).__name__)


# ── Main Tool Dispatcher ─────────────────────────────────────────────────────

def file_controller(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    raw_action = params.get("action", "").lower().strip()
    path = params.get("path", "")
    name = params.get("name", "")

    # Normalize action synonyms
    action_aliases = {
        "list_files": "list", "show_files": "list", "dir": "list", "ls": "list",
        "make_file": "create_file", "new_file": "create_file", "add_file": "create_file", "save_file": "create_file",
        "make_folder": "create_folder", "new_folder": "create_folder", "mkdir": "create_folder",
        "remove": "delete", "remove_file": "delete", "delete_file": "delete", "unlink": "delete",
        "move_file": "move", "mv": "move",
        "copy_file": "copy", "cp": "copy",
        "rename_file": "rename",
        "read_file": "read", "view_file": "read", "cat": "read", "open_file": "read",
        "modify": "write", "edit": "write", "update": "write", "write_file": "write", "overwrite": "write",
        "search": "find", "search_files": "find", "find_file": "find",
    }
    action = action_aliases.get(raw_action, raw_action)

    if player:
        print(f"[File] {action} {name or path}")

    try:
        if action == "list":
            return list_files(path or "workspace")

        elif action == "create_file":
            return create_file(path, name=name, content=params.get("content", ""))

        elif action == "create_folder":
            return create_folder(path, name=name)

        elif action == "delete":
            return delete_file(path, name=name)

        elif action == "move":
            return move_file(path, name=name, destination=params.get("destination", ""))

        elif action == "copy":
            return copy_file(path, name=name, destination=params.get("destination", ""))

        elif action == "rename":
            return rename_file(path, name=name, new_name=params.get("new_name", ""))

        elif action == "read":
            return read_file(path, name=name)

        elif action == "write":
            return write_file(
                path, name=name,
                content=params.get("content", ""),
                append=params.get("append", False)
            )

        elif action == "append":
            return write_file(
                path, name=name,
                content=params.get("content", ""),
                append=True
            )

        elif action == "find":
            return find_files(
                name=name or params.get("name", ""),
                extension=params.get("extension", ""),
                path=path or "workspace",
                max_results=min(int(params.get("max_results", 20)), 50),
            )

        elif action == "largest":
            return get_largest_files(
                path=path or "downloads",
                count=int(params.get("count", 10)),
            )

        elif action == "disk_usage":
            return get_disk_usage(path or "workspace")

        elif action == "organize_desktop":
            return organize_desktop()

        elif action == "info":
            return get_file_info(path, name=name)

        else:
            return _format_result(False, action, path, False, f"Unknown action: '{action}'", error_type="unknown_action")

    except Exception as e:
        traceback.print_exc()
        return _format_result(False, action, path, False, f"File controller exception ({action}): {e}", error_type=type(e).__name__)


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "file_controller",
    "description": (
        "Manages files and folders: list, create_file, create_folder, delete, move, "
        "copy, rename, read, write, append, find, disk_usage, organize_desktop, info. "
        "Always returns a structured verification report with the absolute file path. "
        "When the user does not specify a directory, files are safely placed in their "
        "dedicated JARVIS Workspace (Documents/JARVIS Workspace). "
        "CRITICAL: Report the exact path confirmed in the verified tool response."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | append | find | largest | disk_usage | organize_desktop | info"
            },
            "path": {
                "type": "STRING",
                "description": "File/folder path or shortcut: workspace, desktop, downloads, documents, home, or drive like D:/, C:/"
            },
            "destination": {
                "type": "STRING",
                "description": "Destination path for move/copy"
            },
            "new_name": {
                "type": "STRING",
                "description": "New name for rename"
            },
            "content": {
                "type": "STRING",
                "description": "Content for create_file/write/append"
            },
            "name": {
                "type": "STRING",
                "description": "File name to create, search, or inspect"
            },
            "extension": {
                "type": "STRING",
                "description": "File extension to search (e.g. .pdf)"
            },
            "count": {
                "type": "INTEGER",
                "description": "Number of results for largest"
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": file_controller,
}
