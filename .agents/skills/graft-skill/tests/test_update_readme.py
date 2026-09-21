"""README 生成器的输入保护、格式兼容与只读检查测试。"""

import contextlib
import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
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
        entries = set(self.root.rglob("*"))
        status, output, errors = self.run_main(*arguments)
        self.assertEqual(status, 2)
        self.assertEqual(output, "")
        self.assertTrue(errors)
        self.assertEqual(self.readme.read_bytes(), before)
        self.assertEqual(set(self.root.rglob("*")), entries)

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

    def test_invalid_repo_is_rejected_in_both_modes(self):
        for repo in (None, 123, False, [], {}, "", " \t\n", "\u3000"):
            for arguments in ((), ("--check",)):
                with self.subTest(repo=repo, arguments=arguments):
                    self.seed(config={"bad": {"repo": repo}})
                    self.assert_rejected_without_write(*arguments)

    def test_invalid_description_is_rejected_in_both_modes(self):
        for description in (None, 123, False, [], {}):
            for arguments in ((), ("--check",)):
                with self.subTest(description=description, arguments=arguments):
                    self.seed(config={"bad": {"repo": "owner/repo", "description": description}})
                    self.assert_rejected_without_write(*arguments)

    def test_missing_or_empty_description_is_valid(self):
        for info in ({"repo": "owner/repo"}, {"repo": "owner/repo", "description": ""}):
            with self.subTest(info=info):
                self.seed(config={"valid": info})
                self.assertEqual(self.run_main()[0], 0)
                self.assertIn("| `valid` | [owner/repo](https://github.com/owner/repo) |  |",
                              self.readme.read_text(encoding="utf-8"))
                self.assertEqual(self.run_main("--check")[0], 0)

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

    def test_temporary_file_creation_failure_preserves_readme(self):
        self.seed()
        with patch.object(tempfile, "NamedTemporaryFile", side_effect=OSError(errno.ENOSPC, "disk full")):
            self.assert_rejected_without_write()

    def test_temporary_file_io_failures_preserve_readme_and_cleanup(self):
        real_temporary_file = tempfile.NamedTemporaryFile
        for stage in ("write", "short-write", "flush", "close"):
            with self.subTest(stage=stage):
                self.seed()

                @contextlib.contextmanager
                def failing_temporary_file(*args, **kwargs):
                    with real_temporary_file(*args, **kwargs) as stream:
                        real_write, real_flush = stream.write, stream.flush

                        def partial_write(data):
                            count = real_write(data[:7])
                            real_flush()
                            if stage == "short-write":
                                return count
                            raise OSError(errno.ENOSPC, "partial write: disk full")

                        if stage in ("write", "short-write"):
                            with patch.object(stream, "write", side_effect=partial_write):
                                yield stream
                        elif stage == "flush":
                            with patch.object(stream, "flush", side_effect=OSError(errno.ENOSPC, "flush failed")):
                                yield stream
                        else:
                            yield stream
                    if stage == "close":
                        raise OSError(errno.EIO, "close failed")

                with patch.object(tempfile, "NamedTemporaryFile", side_effect=failing_temporary_file):
                    self.assert_rejected_without_write()

    def test_sync_and_replace_failures_preserve_readme_and_cleanup(self):
        for operation in ("chmod", "fsync", "replace"):
            with self.subTest(operation=operation):
                self.seed()
                with patch.object(os, operation, side_effect=OSError(errno.EIO, operation + " failed")):
                    self.assert_rejected_without_write()

    def test_atomic_replace_uses_synced_closed_file_in_target_directory(self):
        self.seed()
        original = self.readme.read_bytes()
        expected = updater.render(README, CONFIG).encode("utf-8")
        streams, events = [], []
        real_temporary_file, real_fsync, real_replace = tempfile.NamedTemporaryFile, os.fsync, os.replace

        @contextlib.contextmanager
        def tracked_temporary_file(*args, **kwargs):
            with real_temporary_file(*args, **kwargs) as stream:
                streams.append(stream)
                yield stream

        def checked_fsync(fd):
            self.assertEqual(fd, streams[0].fileno())
            # 从另一句柄读到完整内容，验证 flush 发生在 fsync 之前。
            self.assertEqual(Path(streams[0].name).read_bytes(), expected)
            self.assertEqual(self.readme.read_bytes(), original)
            events.append("fsync")
            real_fsync(fd)

        def checked_replace(source, target):
            self.assertEqual(events, ["fsync"])
            self.assertTrue(streams[0].closed)
            self.assertEqual(Path(source).parent, self.readme.parent.resolve())
            self.assertEqual(Path(target), self.readme.resolve())
            self.assertEqual(Path(source).read_bytes(), expected)
            self.assertEqual(self.readme.read_bytes(), original)
            events.append("replace")
            real_replace(source, target)

        with patch.object(tempfile, "NamedTemporaryFile", side_effect=tracked_temporary_file), \
             patch.object(os, "fsync", side_effect=checked_fsync), \
             patch.object(os, "replace", side_effect=checked_replace):
            self.assertEqual(self.run_main(), (0, "updated\n", ""))
        self.assertEqual(events, ["fsync", "replace"])
        self.assertEqual(self.readme.read_bytes(), expected)
        self.assertEqual(set(self.root.iterdir()), {self.readme, self.config})

    @unittest.skipUnless(os.name == "posix", "POSIX permission bits")
    def test_update_preserves_permission_bits(self):
        self.seed()
        self.readme.chmod(0o640)
        self.assertEqual(self.run_main()[0], 0)
        self.assertEqual(stat.S_IMODE(self.readme.stat().st_mode), 0o640)

    def test_update_preserves_readme_symlink(self):
        self.seed()
        target = self.root / "docs" / "README.md"
        target.parent.mkdir()
        self.readme.rename(target)
        try:
            self.readme.symlink_to(Path("docs") / "README.md")
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlinks unavailable: {error}")
        self.assertEqual(self.run_main()[0], 0)
        self.assertTrue(self.readme.is_symlink())
        self.assertEqual(target.read_bytes(), updater.render(README, CONFIG).encode("utf-8"))
        self.assertEqual(list(target.parent.iterdir()), [target])

    def test_no_temporary_file_in_check_mode_or_when_current(self):
        self.seed()
        with patch.object(tempfile, "NamedTemporaryFile") as temporary_file:
            self.assertEqual(self.run_main("--check")[0], 1)
            temporary_file.assert_not_called()
        self.assertEqual(self.run_main()[0], 0)
        with patch.object(tempfile, "NamedTemporaryFile") as temporary_file:
            self.assertEqual(self.run_main("--check")[0], 0)
            self.assertEqual(self.run_main()[0], 0)
            temporary_file.assert_not_called()

    def test_cleanup_failure_reports_leftover_without_masking_write_error(self):
        self.seed()
        original = self.readme.read_bytes()
        with patch.object(os, "fsync", side_effect=OSError(errno.EIO, "original sync error")), \
             patch.object(Path, "unlink", side_effect=PermissionError("cleanup denied")):
            status, output, errors = self.run_main()
        self.assertEqual((status, output), (2, ""))
        self.assertIn("original sync error", errors)
        self.assertIn("cleanup denied", errors)
        self.assertEqual(self.readme.read_bytes(), original)
        leftovers = set(self.root.iterdir()) - {self.readme, self.config}
        self.assertEqual(len(leftovers), 1)
        self.assertIn(str(leftovers.pop()), errors)


if __name__ == "__main__":
    unittest.main()
