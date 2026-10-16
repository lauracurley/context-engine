"""Review tripwires complement runtime policy and content-canary integration tests."""

import ast
import unittest
from pathlib import Path


class BoundaryArchitectureTests(unittest.TestCase):
    def test_usage_module_cannot_acquire_transport_or_client_retrieval_dependencies(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / "context_engine/usage.py").read_text())
        allowed = {
            "json",
            "os",
            "tempfile",
            "datetime",
            "pathlib",
            "",
            "locking",
            "fcntl",
            "contextlib",
        }
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, {"eval", "exec", "__import__"})
                if isinstance(node.func, ast.Attribute):
                    self.assertNotIn(
                        node.func.attr, {"system", "popen", "spawn", "execv", "execve"}
                    )
        self.assertFalse(
            set(imports) - allowed, "Usage dependency expansion needs vendor-boundary review"
        )

    def test_report_schema_rejects_content_at_every_extension_point(self):
        from copy import deepcopy

        from context_engine.usage import Usage, blank, validate

        row = blank()
        report = Usage._report({"search_code": row}, "0")
        validate(report)
        for location in [
            (),
            ("operations",),
            ("operations", "search_code"),
            ("operations", "search_code", "outcomes"),
            ("operations", "search_code", "duration_ms_bins"),
            ("token_usage",),
        ]:
            candidate = deepcopy(report)
            target = candidate
            for key in location:
                target = target[key]
            target["PRIVATE_SOURCE_OR_PATH"] = "CLIENT_CANARY"
            with self.subTest(location=location), self.assertRaises(ValueError):
                validate(candidate)
