"""Offline regression tests for the baseline-preserving audit."""
import csv
import tempfile
import unittest
from pathlib import Path

# Run with python -m unittest discover -s . -p test_subtitle_audit.py
# from the cleanvid directory. The script supports both module and CLI imports.
from scripts.subtitle_audit import episode_identity, existing_windows, union_windows, uncovered, moviehash, audit
from scripts.opensubtitles_provider import ranked_candidates, official_url


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


    def test_provider_rejects_wrong_identity_and_prefers_hash(self):
        def row(id, season=1, episode=1, parent=11280740, **extra):
            return {"attributes":{"feature_details":{"season_number":season,
                    "episode_number":episode,"parent_imdb_id":parent,
                    "parent_title":"Severance"},"language":"en",
                    "release":"Severance S01E01 WEB-DL",
                    "files":[{"file_id":id,"file_name":"Severance.S01E01.en.srt"}],**extra}}
        rows=[row(1,episode=2,moviehash_match=True),row(2,parent=999,moviehash_match=True),
              row(3,foreign_parts_only=True),row(4,ai_translated=True),
              row(5),row(6,moviehash_match=True)]
        matches=ranked_candidates(rows,"Severance",1,1,"Severance.S01E01.WEB-DL",11280740)
        self.assertEqual([m["file_id"] for m in matches],[6,5])
        self.assertTrue(official_url("https://dl.opensubtitles.com/file.srt"))
        self.assertFalse(official_url("https://opensubtitles.com.example.org/file.srt"))

    def test_end_to_end_audit_preserves_baseline_and_rejects_wrong_episode(self):
        def stamp(t):
            m,s=divmod(int(t),60)
            return f"00:{m:02d}:{s:02d},000"
        with tempfile.TemporaryDirectory() as d:
            d=Path(d)
            video=d/"Severance.S01E01.mkv"
            baseline=d/"saved.txt"
            baseline_text="[a:0]volume=enable='between(t,15.000,16.000)':volume=0[a]"
            baseline.write_text(baseline_text)
            transcript=d/"words.csv"
            subs=d/"Severance.S01E01.en.srt"
            wrong=d/"Severance.S01E02.en.srt"
            words=[]
            blocks=[]
            for i in range(40):
                start=5+i*10
                phrase=f"alpha{i} beta{i} gamma{i} delta{i}"
                blocks.append(f"{i+1}\n{stamp(start+2)} --> {stamp(start+4)}\n{phrase}")
                for k,w in enumerate(phrase.split()):
                    words.append({"word":w,"start":start+k*.5,"end":start+k*.5+.5,"confidence":1})
            # Subtitle-only profanity between anchored neighboring cues.
            blocks.append(f"41\n{stamp(77)} --> {stamp(79)}\ndamn!")
            # Independent ASR-only profanity must stay in the union as well.
            words.append({"word":"damn","start":124,"end":124.5,"confidence":.8})
            with transcript.open("w",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=["word","start","end","confidence"])
                writer.writeheader()
                writer.writerows(words)
            subs.write_text("\n\n".join(blocks))
            wrong.write_text(subs.read_text())
            report=audit(video,transcript,baseline,[wrong,subs],["damn"],410)
            self.assertTrue(report["subtitle_verified"])
            self.assertEqual(len(report["accepted"]),1)
            self.assertEqual(len(report["rejected"]),1)
            self.assertEqual(len(report["candidate_additions"]),2)
            self.assertIn((15,16),report["proposed_windows"])
            self.assertEqual(baseline.read_text(),baseline_text)

if __name__=="__main__":
    unittest.main()
