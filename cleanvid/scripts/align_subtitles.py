"""Conservative subtitle/transcription cross-check.

The transcription clock is the video clock. Subtitle cue clocks are estimated
from unique phrase anchors rather than isolated repeated words. Refuse to
silently use a zero offset when a profane cue cannot be aligned reliably.
"""
import argparse
import bisect
import csv
import html
import logging
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
logger = logging.getLogger(__name__)

TOKEN = re.compile(r"[^\W_]+(?:'[^\W_]+)*", re.UNICODE)
TIMING = re.compile(r"(\d+:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d+:\d{2}:\d{2}[,.]\d{1,3})")


def tokens(text):
    text = html.unescape(re.sub(r"<[^>]*>|\{\\[^}]*\}", " ", text))
    text = text.casefold().replace("’", "'").replace("‘", "'")
    return TOKEN.findall(text)


def parse_srt_time(value):
    h, m, s = value.replace(",", ".").split(":")
    return int(h)*3600 + int(m)*60 + float(s)


def parse_srt(srt_path):
    cues = []
    for block in re.split(r"\n\s*\n", Path(srt_path).read_text(encoding="utf-8-sig").replace("\r\n", "\n").strip()):
        lines = block.splitlines()
        for i, line in enumerate(lines):
            match = TIMING.search(line)
            if match:
                start, end = map(parse_srt_time, match.groups())
                if start < end:
                    cues.append(dict(start=start, end=end, text=" ".join(lines[i+1:])))
                break
    if not cues:
        raise ValueError(f"No valid cues in {srt_path}")
    return sorted(cues, key=lambda c: c["start"])


def occurrences(seq, lexicon):
    """Return every matching configured word or phrase (including repetitions)."""
    for i in range(len(seq)):
        for phrase in lexicon.get(seq[i], ()):
            if tuple(seq[i:i+len(phrase)]) == phrase:
                yield i, phrase


def make_lexicon(swear_list):
    out = defaultdict(set)
    for value in swear_list:
        phrase = tuple(tokens(value))
        if phrase:
            out[phrase[0]].add(phrase)
    return out


def find_profanity_in_subs(subs, swear_list):
    lexicon = make_lexicon(swear_list)
    return [cue for cue in subs if any(occurrences(tokens(cue["text"]), lexicon))]


def timed_tokens(words):
    return [(token, float(w["start"]), float(w["end"]))
            for w in sorted(words, key=lambda w: w["start"])
            for token in tokens(w["word"]) if float(w["end"]) >= float(w["start"])]


def phrase_anchors(words, subs, n=4):
    """One anchor per cue; require unique exact n-grams in BOTH sequences."""
    speech = timed_tokens(words)
    seq = [w[0] for w in speech]
    asr_index = defaultdict(list)
    for i in range(len(seq)-n+1):
        # Reject anchors spanning dialogue gaps.
        if speech[i+n-1][2]-speech[i][1] <= 12:
            asr_index[tuple(seq[i:i+n])].append(i)
    cue_index = defaultdict(list)
    for cue_id, cue in enumerate(subs):
        ts = tokens(cue["text"])
        for i in range(len(ts)-n+1):
            cue_index[tuple(ts[i:i+n])].append((cue_id, i, len(ts)))
    candidates = defaultdict(list)
    for phrase, locations in cue_index.items():
        hits = asr_index.get(phrase, [])
        if len(locations) != 1 or len(hits) != 1:
            continue
        ci, j, count = locations[0]
        cue, i = subs[ci], hits[0]
        # Cue time is only approximate; estimate the phrase midpoint within it.
        subtitle_mid = cue["start"] + (cue["end"]-cue["start"])*(j+n/2)/count
        speech_mid = (speech[i][1]+speech[i+n-1][2])/2
        candidates[ci].append(subtitle_mid-speech_mid)
    anchors = []
    for ci, offsets in candidates.items():
        if max(offsets)-min(offsets) <= 2.0:
            cue = subs[ci]
            anchors.append(((cue["start"]+cue["end"])/2, statistics.median(offsets)))
    # Eliminate isolated anchors using adjacent corroboration. Do not average
    # across a detected edit/cut or assume there is no drift.
    anchors.sort()
    reliable = []
    for i, (t, off) in enumerate(anchors):
        neighbors = anchors[max(0, i-4):i] + anchors[i+1:i+5]
        if sum(abs(t-u) <= 240 and abs(off-v) <= 2.0+0.003*abs(t-u)
               for u,v in neighbors) >= 2:
            reliable.append((t, off))
    return reliable


def calculate_offset(words, subs):
    anchors = phrase_anchors(words, subs)
    if len(anchors) < 3:
        raise ValueError("Insufficient corroborated subtitle anchors")
    return statistics.median(o for _, o in anchors)


def local_offset(anchors, t):
    local = [(u,o) for u,o in anchors if abs(u-t) <= 180]
    if len(local) < 3:
        raise ValueError(f"No reliable local subtitle alignment near {t:.2f}s")
    near = sorted(local, key=lambda p: abs(p[0]-t))[:7]
    offsets = [o for _,o in near]
    median = statistics.median(offsets)
    if max(offsets)-min(offsets) > 2.5:
        raise ValueError(f"Subtitle alignment discontinuity near {t:.2f}s; review release or offset")
    # A nearby robust estimate plus uncertainty margin is safer than applying
    # one global offset to an entire episode with drift.
    uncertainty = max(0.5, max(abs(o-median) for o in offsets)+0.25)
    return median, uncertainty


def crosscheck(words, subs, swear_list):
    """Return additions only; never discard original ASR word timestamps."""
    lexicon = make_lexicon(swear_list)
    flagged = [(cue, list(occurrences(tokens(cue["text"]), lexicon))) for cue in subs]
    flagged = [(cue, hits) for cue, hits in flagged if hits]
    anchors = phrase_anchors(words, subs)
    if len(anchors) < 3:
        raise ValueError("Subtitle synchronization is unverified")
    # A wrong episode with matching opening credits must not pass the audit.
    if len(subs) >= 30:
        span = subs[-1]["end"]-subs[0]["start"]
        tolerance = min(180, 0.25*span)
        if (len(anchors) < 5 or anchors[0][0]-subs[0]["start"] > tolerance
                or subs[-1]["end"]-anchors[-1][0] > tolerance
                or anchors[-1][0]-anchors[0][0] < 0.5*span):
            raise ValueError("Insufficient episode-wide subtitle alignment")
    masked = re.compile(r"(?<!\w)(?:[a-z]*\*{2,}[a-z]*|[a-z]+\*+[a-z]+)(?!\w)", re.I)
    for cue in subs:
        if masked.search(re.sub(r"<[^>]*>", "", cue["text"])):
            raise ValueError(f"Potentially masked profanity at {cue['start']:.2f}s; review the uncensored subtitle or audio")
    if not flagged:
        return []
    speech = timed_tokens(words)
    seq = [w[0] for w in speech]
    # Only exact ASR lexicon hits are evidence of coverage. An arbitrary
    # substring or one earlier repetition cannot satisfy another occurrence.
    detected = defaultdict(list)
    for i, phrase in occurrences(seq, lexicon):
        j = i+len(phrase)-1
        if (speech[j][2]-speech[i][1] <= max(2.0, 1.0*len(phrase))
                and speech[j][2] > speech[i][1]
                and all(speech[k+1][1]-speech[k][2] <= 1.0 for k in range(i,j))):
            detected[phrase].append((i, j, speech[i][1], speech[j][2]))
    used = set()
    additions = []
    for cue, hits in flagged:
        offset, uncertainty = local_offset(anchors, (cue["start"]+cue["end"])/2)
        start = cue["start"]-offset
        end = cue["end"]-offset
        for _, phrase in hits:
            # Phrases longer than two words may not be recognized by the
            # downstream legacy mute generator. Inject them conservatively.
            choices = [(i,j,s,e) for i,j,s,e in detected[phrase]
                       if (i,j) not in used and s >= start-0.2 and e <= end+0.2
                       and len(phrase) <= 2]
            if choices:
                i,j,_,_ = min(choices, key=lambda x: abs((x[2]+x[3])/2-(start+end)/2))
                used.add((i,j))
            else:
                additions.append(dict(word=" ".join(phrase), start=max(0,start-uncertainty),
                                      end=max(0,end+uncertainty), confidence=0.0))
    return additions


def inject_subtitles_into_words(csv_path, srt_path, output_path=None):
    import utils
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        words = [dict(word=row["word"], start=float(row["start"]),
                      end=float(row["end"]), confidence=float(row.get("confidence") or 0))
                 for row in csv.DictReader(f)]
    # Strict cross-check: all configured swear-list entries, including those
    # previously treated as subtitle exceptions. Original ASR hits are retained.
    additions = crosscheck(words, parse_srt(srt_path), utils.parse_swears())
    if not additions:
        logger.info("No additional configured profanity found in subtitles")
        return None
    if output_path is None:
        p = Path(csv_path)
        output_path = p.with_name(p.stem+"_aligned.csv")
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["start", "end", "word", "confidence"])
        writer.writeheader()
        writer.writerows(sorted(words+additions, key=lambda w: w["start"]))
    logger.info("Added %d conservative subtitle-derived intervals", len(additions))
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv")
    p.add_argument("srt")
    p.add_argument("--output", "-o")
    args = p.parse_args()
    inject_subtitles_into_words(args.csv, args.srt, args.output)
