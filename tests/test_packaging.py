import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "extension_package", REPO / "vscode-extension/scripts/package.py"
)
PACKAGING = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGING)


class PackagingTests(unittest.TestCase):
    def test_package_allowlist_excludes_unrelated_data(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory).resolve()
            extension = repo / "vscode-extension"
            for folder in (repo / "context_engine", extension / "src", extension / "media"):
                folder.mkdir(parents=True)
            (repo / "context_engine/__init__.py").write_text('"""Fixture engine."""\n')
            (repo / "context_engine/.env").write_text("PRIVATE_SENTINEL")
            (repo / "context_engine/local.sqlite").write_text("PRIVATE_SENTINEL")
            (extension / "src/extension.js").write_text("module.exports = {};\n")
            (extension / "src/notes.json").write_text("PRIVATE_SENTINEL")
            (extension / "media/workbench.css").write_text("body {}\n")
            (extension / "media/notes.txt").write_text("PRIVATE_SENTINEL")
            package = json.loads((REPO / "vscode-extension/package.json").read_text())
            (extension / "package.json").write_text(json.dumps(package))
            for file in ("README.md", "CHANGELOG.md"):
                (extension / file).write_text("Test\n")
            with patch.object(PACKAGING, "ROOT", extension), patch.object(PACKAGING, "REPO", repo):
                archive = PACKAGING.build()
            with zipfile.ZipFile(archive) as result:
                self.assertIn("extension/backend/context_engine/__init__.py", result.namelist())
                self.assertIn("extension/media/workbench.css", result.namelist())
                self.assertFalse(
                    any(b"PRIVATE_SENTINEL" in result.read(name) for name in result.namelist())
                )

    def test_symlink_package_inputs_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "outside.py").write_text("PRIVATE_SENTINEL")
            (root / "assets").mkdir()
            (root / "assets/link.py").symlink_to(root / "outside.py")
            with self.assertRaisesRegex(ValueError, "symlink"):
                list(PACKAGING.allowed_files(root / "assets", {".py"}))

    def test_bundle_preserves_backend_build_identity(self):
        import shutil

        from context_engine import runtime_identity

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory).resolve()
            extension = repo / "vscode-extension"
            shutil.copytree(
                REPO / "context_engine",
                repo / "context_engine",
                ignore=shutil.ignore_patterns("__pycache__"),
            )
            extension.mkdir()
            for name in ("src", "media"):
                (extension / name).mkdir()
            for name in ("package.json", "README.md", "CHANGELOG.md"):
                shutil.copyfile(REPO / "vscode-extension" / name, extension / name)
            with patch.object(PACKAGING, "ROOT", extension), patch.object(PACKAGING, "REPO", repo):
                archive = PACKAGING.build()
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(repo / "unpacked")
            self.assertEqual(
                runtime_identity.BUILD,
                runtime_identity.source_build(repo / "unpacked/extension/backend/context_engine"),
            )
