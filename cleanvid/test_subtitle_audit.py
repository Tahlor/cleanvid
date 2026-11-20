"""Offline regression tests for the baseline-preserving audit."""
import tempfile
import unittest
from pathlib import Path

# Run with python -m unittest discover -s . -p test_subtitle_audit.py
# from the cleanvid directory. The script supports both module and CLI imports.
from scripts.subtitle_audit import episode_identity, existing_windows, union_windows, uncovered, moviehash


class AuditTests(unittest.TestCase):
    def test_episode_identity(self):
        self.assertEqual(episode_identity("Severance.S01E02.Half.Loop.mkv"), ("Severance",1,2))
        with self.assertRaises(ValueError):
            episode_identity("Severance.S01E02E03.mkv")

    def test_baseline_preserve(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"saved.txt"
            content="[a:0]volume=enable='between(t,5.000,6.000)':volume=0[a]\n"
            p.write_text(content)
            self.assertEqual(existing_windows(p),[(5.0,6.0)])
            self.assertFalse(uncovered((5.1,5.9),existing_windows(p)))
            self.assertTrue(uncovered((5.1,6.2),existing_windows(p)))
            self.assertEqual(union_windows(existing_windows(p)+[(5.5,7)]),[(5.0,7)])
            self.assertEqual(p.read_text(),content)
            p.write_text("[a:0]volume=0[a]")
            with self.assertRaises(ValueError):
                existing_windows(p)

    def test_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"zero.bin"
            p.write_bytes(bytes(131072))
            self.assertEqual(moviehash(p),"0000000000020000")

if __name__=="__main__":
    unittest.main()
