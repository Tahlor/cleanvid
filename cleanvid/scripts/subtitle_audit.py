"""Discover, verify and audit subtitles against an existing mute list.

No cloud transcription is initiated here. Existing mute windows are immutable.
Only a separate, explicitly requested output filter can contain proposed additions.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from collections import Counter
from statistics import median

from align_subtitles import (parse_srt, timed_tokens, tokens, make_lexicon,
                             occurrences, phrase_anchors, crosscheck, local_offset)

EPISODE = re.compile(r"(?i)(?<![a-z0-9])s(\d{1,2})e(\d{1,3})(?!\d|e\d)")
WINDOW = re.compile(r"volume=enable='between\(t,(-?[\d.]+),(-?[\d.]+)\)':volume=0")
LABELS = re.compile(r"^\[(?:0:)?a:\d+\](.*)\[a\]$", re.S)


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def moviehash(path):
    """OpenSubtitles fingerprint (size + first/last 64 KiB uint64 sums)."""
    path = Path(path)
    size = path.stat().st_size
    if size < 131072:
        raise ValueError("File too small for OpenSubtitles hash")
    with path.open("rb") as f:
        head = f.read(65536)
        f.seek(-65536, 2)
        tail = f.read(65536)
    return f"{(size+sum(struct.unpack('<8192Q',head))+sum(struct.unpack('<8192Q',tail))) & ((1<<64)-1):016x}"


def episode_identity(path):
    match = EPISODE.search(Path(path).stem)
    if not match:
        raise ValueError("Expected unambiguous SxxEyy in video filename")
    tail = Path(path).stem[match.end():]
    if re.match(r"(?i)[.\- _]*(?:e\d+|s\d+e\d+)",tail):
        raise ValueError("Multi-episode video requires review")
    title = re.sub(r"[._]+", " ", Path(path).stem[:match.start()]).strip(" -")
    if not title:
        title = Path(path).parent.name
    return title, int(match[1]), int(match[2])


def load_words(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        words = [dict(word=r["word"], start=float(r["start"]), end=float(r["end"]),
                      confidence=float(r.get("confidence") or 0)) for r in csv.DictReader(f)]
    if len(words) < 30:
        raise ValueError("Transcript too short to verify an episode")
    return words


def existing_windows(path):
    text = Path(path).read_text(encoding="utf-8-sig").strip()
    labels = LABELS.fullmatch(text)
    if not labels:
        raise ValueError("Unrecognized original mute filter; do not replace it")
    body = labels[1]
    if not body or body == "anull":
        return []
    chunks = WINDOW.findall(body)
    if not chunks:
        raise ValueError("No parseable mute intervals")
    if WINDOW.sub("",body).replace(",",""):
        raise ValueError("Unexpected filters in baseline; require manual review")
    result = [(max(0,float(a)),float(b)) for a,b in chunks]
    if any(b<=a for a,b in result):
        raise ValueError("Invalid baseline intervals")
    return result


def union_windows(windows):
    out = []
    for a,b in sorted(windows):
        if out and a <= out[-1][1]+.02:
            out[-1] = (out[-1][0], max(b,out[-1][1]))
        else:
            out.append((a,b))
    return out


def uncovered(interval, covered, tolerance=.04):
    a,b=interval
    for l,r in covered:
        if r < a:
            continue
        if l > a+tolerance:
            return True
        a=max(a,r)
        if a >= b-tolerance:
            return False
    return a < b-tolerance


def audit_candidate(video, words, candidate, lexicon, duration):
    candidate=Path(candidate)
    _, season, episode=episode_identity(video)
    match=EPISODE.search(candidate.stem)
    if match and (int(match[1]),int(match[2])) != (season,episode):
        raise ValueError("Subtitle filename identifies a different episode")
    cues=parse_srt(candidate)
    if len(cues)<30:
        raise ValueError("Subtitle has too few cues for full episode")
    if cues[-1]["end"] > duration+120 or cues[-1]["end"] < duration*.65:
        raise ValueError("Subtitle duration appears inconsistent with source")
    anchors=phrase_anchors(words,cues)
    if len(anchors)<8:
        raise ValueError("Insufficient independent matching phrase anchors")
    # Require corroboration in the beginning, middle and end; verify local
    # timing of profanity through crosscheck rather than trusting the title/hash.
    span=cues[-1]["end"]-cues[0]["start"]
    bins={min(3,int(4*(t-cues[0]["start"])/span)) for t,_ in anchors}
    if len(bins)<4:
        raise ValueError("Subtitle alignment does not cover all four episode quarters")
    additions=crosscheck(words,cues,lexicon)
    return dict(path=str(candidate), sha256=file_sha(candidate), cues=len(cues),
                anchor_count=len(anchors), anchor_span=[anchors[0][0],anchors[-1][0]],
                median_offset=median(o for _,o in anchors), additions=additions)


def speech_hits(words, swear_list, duration):
    speech=timed_tokens(words)
    seq=[w[0] for w in speech]
    hits=[]
    for i, phrase in occurrences(seq,make_lexicon(swear_list)):
        j=i+len(phrase)-1
        if any(speech[k+1][1]-speech[k][2]>1 for k in range(i,j)):
            continue
        hits.append(dict(start=max(0,speech[i][1]),end=min(duration,max(speech[j][2],speech[i][1]+.2)),
                         source="ASR", word=" ".join(phrase)))
    return hits


def discover_local(video):
    video=Path(video)
    candidates=[]
    for p in video.parent.glob("*.srt"):
        if p.stem==video.stem or p.stem.startswith(video.stem+"."):
            candidates.append(p)
    return sorted(candidates)


def download_subtitle(video):
    """Use the official OpenSubs CLI; credentials stay in its OS keychain."""
    exe=shutil.which("opensubs") or shutil.which("opensubs.cmd")
    if not exe:
        raise RuntimeError("Install official opensubs-cli (npm install -g opensubs-cli), configure its keychain, then retry")
    # Single file, one English download at a time; never use an unlimited bulk
    # download or overwrite existing local subtitle files.
    subprocess.run([exe,str(video),"-l","en","-N"], check=True, timeout=180)
    candidates=discover_local(video)
    if not candidates:
        raise RuntimeError("Provider returned no local English SRT; check account quota")
    return candidates


def duration_seconds(video):
    p=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                      "-of","default=noprint_wrappers=1:nokey=1",str(video)],
                     capture_output=True,text=True,check=True,timeout=30)
    return float(p.stdout.strip())


def audit(video, transcript, baseline, candidates, swear_list, duration):
    baseline_windows=union_windows(existing_windows(baseline))
    words=load_words(transcript)
    accepted=[]
    rejected=[]
    for c in candidates:
        try:
            accepted.append(audit_candidate(video,words,c,swear_list,duration))
        except (ValueError,OSError,UnicodeError) as exc:
            rejected.append(dict(path=str(c),reason=str(exc)))
    accepted.sort(key=lambda x:x["anchor_count"],reverse=True)
    hits=speech_hits(words,swear_list,duration)
    for item in accepted:
        for w in item["additions"]:
            hits.append(dict(start=w["start"],end=min(duration,w["end"]),source=item["path"],word=w["word"]))
    additions=[]
    for hit in hits:
        a=max(0,hit["start"]-.10)
        b=min(duration,hit["end"]+.10)
        if b>a and uncovered((a,b),baseline_windows):
            additions.append(dict(start=a,end=b,source=hit["source"]))
    combined=union_windows(baseline_windows+[(w["start"],w["end"]) for w in additions])
    # No subtitle accepted is a failed audit even if ASR produced candidates.
    return dict(video=str(video),episode=episode_identity(video),
                baseline=str(baseline),baseline_sha256=file_sha(baseline),
                transcript=str(transcript),transcript_sha256=file_sha(transcript),
                accepted=accepted,rejected=rejected,
                subtitle_verified=bool(accepted),baseline_windows=baseline_windows,
                candidate_additions=additions,proposed_windows=combined)


def atomic_text(path, text):
    path=Path(path)
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite {path}")
    path.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive create; caller uses new audit output names.
    with path.open("x",encoding="utf-8") as f:
        f.write(text)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video",required=True,type=Path)
    p.add_argument("--transcript",required=True,type=Path)
    p.add_argument("--mute-list",required=True,type=Path)
    p.add_argument("--subtitle",action="append",default=[],type=Path)
    p.add_argument("--download",action="store_true",
                   help="Use official OpenSubs CLI if no local candidate exists")
    p.add_argument("--report",required=True,type=Path)
    p.add_argument("--proposed-filter",type=Path)
    args=p.parse_args()
    candidates=args.subtitle or discover_local(args.video)
    if not candidates and args.download:
        candidates=download_subtitle(args.video)
    swear_path=Path(__file__).resolve().parent.parent/"swears.txt"
    swears=[line.split("|",1)[0].strip() for line in swear_path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
    report=audit(args.video,args.transcript,args.mute_list,candidates,swears,duration_seconds(args.video))
    atomic_text(args.report,json.dumps(report,indent=2))
    print(f"Subtitle candidates accepted: {len(report['accepted'])}; rejected: {len(report['rejected'])}; "
          f"candidate additions: {len(report['candidate_additions'])}")
    if not report["subtitle_verified"]:
        print("UNVERIFIED: no correctly aligned subtitle; baseline unchanged",file=sys.stderr)
        return 2
    if args.proposed_filter:
        if args.proposed_filter.resolve()==args.mute_list.resolve():
            raise ValueError("Cannot overwrite baseline mute list")
        body=",".join(f"volume=enable='between(t,{a:.3f},{b:.3f})':volume=0"
                      for a,b in report["proposed_windows"]) or "anull"
        atomic_text(args.proposed_filter,f"[a:0]{body}[a]\n")
    print("Audit complete: review candidate additions before rendering; never a guarantee of zero missed speech.")
    return 0


if __name__=="__main__":
    sys.exit(main())
