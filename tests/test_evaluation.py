import unittest

from evaluate_retrieval import literal_search, score


class EvaluationTests(unittest.TestCase):
    def test_metrics_penalize_false_positives_misses_and_duplicates(self):
        s = score(["api/a.py", "worker/b.py"], ["wrong/c.py", "api/a.py", "api/a.py"])
        self.assertEqual((s["precision"], s["recall"], s["reciprocal_rank"]), (0.5, 0.5, 0.5))
        self.assertFalse(s["exact_files"])
        self.assertTrue(score([], [])["exact_files"])
        self.assertFalse(score([], ["api/a.py"])["exact_files"])
        self.assertEqual(score(["api/a.py"], [])["recall"], 0)

    def test_literal_baseline_is_case_insensitive_and_budgeted(self):
        files = {("api", "a.py"): {"text": 'CODE = "UPPER"\n', "hash": "hash", "revision": None}}
        sources = {"api": {"root": "/fixture"}}
        self.assertEqual(len(literal_search(files, sources, "upper", 8000)["items"]), 1)
        self.assertEqual(literal_search(files, sources, "missing", 8000)["items"], [])
        self.assertEqual(literal_search(files, sources, "upper", 1)["items"], [])
