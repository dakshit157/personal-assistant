import json
import os
import shutil
import unittest
from pathlib import Path

from actions.file_controller import (
    create_file,
    create_folder,
    write_file,
    read_file,
    delete_file,
    list_files,
    find_files,
    get_disk_usage,
    file_controller,
    _DEFAULT_WORKSPACE,
)

class TestFilesystemRepair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = _DEFAULT_WORKSPACE / "automated_tests"
        cls.test_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_default_workspace_used_for_bare_filename(self):
        filename = "test_bare_default.txt"
        target_path = _DEFAULT_WORKSPACE / filename
        if target_path.exists():
            target_path.unlink()

        raw_res = create_file(filename, content="Default workspace content")
        data = json.loads(raw_res)

        self.assertTrue(data.get("success"), f"Failed: {raw_res}")
        self.assertTrue(data.get("verified"))
        self.assertEqual(data.get("operation"), "create_file")
        self.assertEqual(Path(data["path"]).resolve(), target_path.resolve())
        self.assertTrue(target_path.exists())
        self.assertGreater(data.get("size_bytes", 0), 0)

        # Cleanup
        target_path.unlink(missing_ok=True)

    def test_create_and_verify_file_content(self):
        filepath = self.test_dir / "notes.txt"
        content = "JARVIS Diagnostic Protocol: OK\nAll systems nominal."
        raw_res = create_file(str(filepath), content=content)
        data = json.loads(raw_res)

        self.assertTrue(data["success"])
        self.assertTrue(data["verified"])
        self.assertEqual(data["size_bytes"], filepath.stat().st_size)
        self.assertGreater(data["size_bytes"], 0)
        self.assertTrue(filepath.is_file())

        # Verify reading returns exact content
        read_res = read_file(str(filepath))
        read_data = json.loads(read_res)
        self.assertTrue(read_data["success"])
        self.assertIn("JARVIS Diagnostic Protocol: OK", read_data["content"])

    def test_create_folder_and_subdirectories(self):
        nested_dir = self.test_dir / "sub1" / "sub2" / "sub3"
        raw_res = create_folder(str(nested_dir))
        data = json.loads(raw_res)

        self.assertTrue(data["success"])
        self.assertTrue(data["verified"])
        self.assertTrue(nested_dir.is_dir())

    def test_append_file_updates_bytes_and_content(self):
        filepath = self.test_dir / "append_test.log"
        create_file(str(filepath), content="Line 1\n")

        raw_append = write_file(str(filepath), content="Line 2\n", append=True)
        data = json.loads(raw_append)

        self.assertTrue(data["success"])
        self.assertTrue(data["verified"])
        self.assertEqual(data["size_bytes"], filepath.stat().st_size)
        self.assertGreater(data["size_bytes"], 0)

        read_res = read_file(str(filepath))
        read_data = json.loads(read_res)
        self.assertIn("Line 1\nLine 2\n", read_data["content"])

    def test_d_drive_and_c_drive_allowed(self):
        # D: drive path
        d_test_file = Path(__file__).resolve().parent.parent / "scratch" / "d_drive_test.txt"
        d_test_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            raw_res = create_file(str(d_test_file), content="D drive verification")
            data = json.loads(raw_res)
            self.assertTrue(data["success"])
            self.assertTrue(data["verified"])
            self.assertTrue(d_test_file.exists())
        finally:
            d_test_file.unlink(missing_ok=True)

    def test_protected_system_paths_rejected(self):
        sys_root = os.environ.get("SystemRoot", "C:\\Windows")
        dangerous_path = Path(sys_root) / "System32" / "jarvis_hack.dll"
        raw_res = create_file(str(dangerous_path), content="malicious")
        data = json.loads(raw_res)

        self.assertFalse(data["success"])
        self.assertFalse(data["verified"])
        self.assertIn("Access denied", data["message"])
        self.assertFalse(dangerous_path.exists())

    def test_file_controller_dispatcher_synonyms(self):
        # Test synonyms normalized by dispatcher
        p1 = self.test_dir / "dispatcher_test.txt"
        r1 = file_controller({"action": "make_file", "path": str(p1), "content": "synonym test"})
        d1 = json.loads(r1)
        self.assertTrue(d1["success"])
        self.assertTrue(p1.exists())

        r2 = file_controller({"action": "modify", "path": str(p1), "content": "modified content"})
        d2 = json.loads(r2)
        self.assertTrue(d2["success"])
        self.assertIn("modified content", p1.read_text(encoding="utf-8"))

        r3 = file_controller({"action": "delete_file", "path": str(p1)})
        d3 = json.loads(r3)
        self.assertTrue(d3["success"])
        self.assertFalse(p1.exists())

if __name__ == "__main__":
    unittest.main()
