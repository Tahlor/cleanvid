"""Regression tests for subtitle cross-check, independent of cloud credentials."""
import unittest
from scripts.align_subtitles import crosscheck, tokens, phrase_anchors, parse_srt
from pathlib import Path
from tempfile import TemporaryDirectory


def fixture(offset=3.0):
    phrases = [
        "unique alpha river bridge",
        "bright yellow garden ladder",
        "quiet silver marble window",
        "crimson folded paper lantern",
        "winter wooden empty basket",
        "careful distant morning whisper",
    ]
    words, cues = [], []
    for i, p in enumerate(phrases):
        t = 10.0+i*15
        cues.append(dict(text=p, start=t+offset, end=t+offset+2))
        for k, w in enumerate(p.split()):
            words.append(dict(word=w, start=t+k*.5, end=t+k*.5+.5, confidence=1))
    return words, cues


class AlignmentTests(unittest.TestCase):
    def test_tokenization(self):
        self.assertEqual(tokens("<i>He’ll</i>—never!"), ["he'll","never"])

    def test_repeated_profanity_needs_distinct_hits(self):
        words, cues = fixture()
        words.append(dict(word="damn", start=33.0, end=33.3, confidence=.9))
        cues.append(dict(text="damn, damn!", start=35.8, end=37.2))
        additions = crosscheck(words, sorted(cues, key=lambda c:c["start"]), ["damn"])
        self.assertEqual(len(additions), 1)
        self.assertLessEqual(additions[0]["start"], 33)
        self.assertGreater(additions[0]["end"], 34)

    def test_subtitle_only_phrase(self):
        words, cues = fixture()
        cues.append(dict(text="go to hell", start=36, end=37))
        additions = crosscheck(words, sorted(cues, key=lambda c:c["start"]), ["go to hell"])
        self.assertEqual(len(additions), 1)
        self.assertEqual(additions[0]["word"], "go to hell")

    def test_wrong_release_does_not_pass(self):
        words, cues = fixture()
        with self.assertRaises(ValueError):
            crosscheck(words, [dict(text="unrelated material", start=1,end=3)], ["damn"])

    def test_masked_profanity_requires_review(self):
        words,cues=fixture()
        cues.append(dict(text="d**n", start=36,end=37))
        with self.assertRaises(ValueError):
            crosscheck(words, sorted(cues,key=lambda c:c["start"]), ["damn"])

    def test_unicode_srt(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"test.srt"
            p.write_text("1\n00:00:01,000 --> 00:00:02,100\nHe’ll be here.\n",encoding="utf-8-sig")
            self.assertEqual(parse_srt(p)[0]["end"],2.1)

if __name__ == "__main__":
    unittest.main()
