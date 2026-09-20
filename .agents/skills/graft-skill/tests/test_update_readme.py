"""README 生成器的输入保护、格式兼容与只读检查测试。"""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update-readme.py"
SPEC = importlib.util.spec_from_file_location("update_readme", SCRIPT)
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)

BEGIN, END = updater.BEGIN, updater.END
CONFIG = {
    "stable": {"repo": "owner/stable", "description": "中文说明"},
    ".experimental/trial": {"repo": "owner/trial", "description": "试验说明"},
}
README = f"# Skills\n手动内容{BEGIN}\n旧表格\n{END}\n安装说明\n"


class UpdateReadmeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.readme = self.root / "README.md"
        self.config = self.root / "grafted-skills.json"
        self.root_patch = patch.object(updater, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def seed(self, readme=README, config=CONFIG):
        self.readme.write_bytes(readme.encode("utf-8"))
        self.config.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    def run_main(self, *arguments):
        output, errors = io.StringIO(), io.StringIO()
        with patch("sys.argv", [str(SCRIPT), *arguments]):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                status = updater.main()
        return status or 0, output.getvalue(), errors.getvalue()

    def assert_rejected_without_write(self, *arguments):
        before = self.readme.read_bytes()
        status, _, errors = self.run_main(*arguments)
        self.assertNotEqual(status, 0)
        self.assertTrue(errors)
        self.assertEqual(self.readme.read_bytes(), before)

    def test_missing_config_is_rejected_without_write(self):
        self.readme.write_bytes(README.encode("utf-8"))
        self.assert_rejected_without_write()

    def test_missing_readme_is_rejected(self):
        self.config.write_text("{}", encoding="utf-8")
        status, _, errors = self.run_main()
        self.assertNotEqual(status, 0)
        self.assertTrue(errors)
        self.assertFalse(self.readme.exists())

    def test_invalid_json_is_rejected_without_write(self):
        self.seed()
        self.config.write_text("{invalid", encoding="utf-8")
        self.assert_rejected_without_write()

    def test_invalid_config_shape_is_rejected_without_write(self):
        for config in ([], None, {"bad": None}, {"bad": {}}):
            with self.subTest(config=config):
                self.seed(config=config)
                self.assert_rejected_without_write()

    def test_missing_markers_are_rejected_without_write(self):
        for readme in ("# no markers", BEGIN + "\ntext", "text\n" + END):
            with self.subTest(readme=readme):
                self.seed(readme=readme)
                self.assert_rejected_without_write()

    def test_duplicate_markers_are_rejected_without_write(self):
        for readme in (README + BEGIN, README + END):
            with self.subTest(readme=readme):
                self.seed(readme=readme)
                self.assert_rejected_without_write()

    def test_reversed_markers_are_rejected_without_write(self):
        self.seed(readme=f"before{END}\nmiddle\n{BEGIN}\nafter")
        self.assert_rejected_without_write()

    def test_invalid_utf8_is_rejected_without_write(self):
        for target in ("README.md", "grafted-skills.json"):
            with self.subTest(target=target):
                self.seed()
                (self.root / target).write_bytes(bytes([0xff]))
                self.assert_rejected_without_write()

    def test_update_preserves_manual_content_and_rendering(self):
        self.seed()
        status, output, errors = self.run_main()
        self.assertEqual(status, 0)
        self.assertIn("updated", output)
        self.assertEqual(errors, "")
        result = self.readme.read_text(encoding="utf-8")
        expected = README.split(BEGIN)[0] + BEGIN + "\n" + updater.build(CONFIG) + END + README.split(END)[1]
        self.assertEqual(result, expected)
        self.assertIn("| `stable` | [owner/stable]", result)
        self.assertIn("| `trial` | [owner/trial]", result)

    def test_second_update_does_not_rewrite(self):
        self.seed()
        self.run_main()
        before = self.readme.stat().st_mtime_ns
        status, output, errors = self.run_main()
        self.assertEqual((status, output, errors), (0, "", ""))
        self.assertEqual(self.readme.stat().st_mtime_ns, before)

    def test_explicit_empty_config_can_clear_generated_rows(self):
        self.seed(config={})
        self.assertEqual(self.run_main()[0], 0)
        expected = README.split(BEGIN)[0] + BEGIN + "\n" + END + README.split(END)[1]
        self.assertEqual(self.readme.read_text(encoding="utf-8"), expected)

    def test_check_reports_drift_without_write(self):
        self.seed()
        before = self.readme.read_bytes()
        status, output, errors = self.run_main("--check")
        self.assertEqual(status, 1)
        self.assertTrue(output or errors)
        self.assertEqual(self.readme.read_bytes(), before)

    def test_check_passes_without_rewrite_when_current(self):
        self.seed()
        self.run_main()
        before = self.readme.stat().st_mtime_ns
        self.assertEqual(self.run_main("--check")[0], 0)
        self.assertEqual(self.readme.stat().st_mtime_ns, before)

    def test_check_rejects_invalid_inputs_without_write(self):
        self.seed(readme=END + "\n" + BEGIN)
        self.assert_rejected_without_write("--check")

    def test_crlf_is_preserved(self):
        self.seed(readme=README.replace("\n", "\r\n"))
        self.assertEqual(self.run_main()[0], 0)
        result = self.readme.read_bytes()
        self.assertNotIn(b"\n", result.replace(b"\r\n", b""))
        self.assertEqual(self.run_main("--check")[0], 0)


if __name__ == "__main__":
    unittest.main()
