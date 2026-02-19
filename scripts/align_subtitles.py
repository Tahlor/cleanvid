import re
import csv
import logging
import sys
import os
from pathlib import Path
from datetime import timedelta

# Add root directory to sys.path to allow imports from parent
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

import utils

# Setup logging
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_srt_time(time_str):
    """Converts SRT timestamp '00:00:00,000' to seconds (float)."""
    hours, minutes, seconds = time_str.replace(',', '.').split(':')
    return float(hours) * 3600 + float(minutes) * 60 + float(seconds)

def parse_srt(srt_path):
    """Parses an SRT file and returns a list of (start, end, text) tuples."""
    subs = []
    with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Simple regex for SRT blocks
    # Index
    # Start --> End
    # Text...
    
    pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n((?:(?!\d+\n\d{2}:\d{2}:\d{2},\d{3}).)*)', re.DOTALL)
    
    matches = pattern.findall(content)
    for index, start_str, end_str, text in matches:
        start = parse_srt_time(start_str)
        end = parse_srt_time(end_str)
        text = text.strip().replace('\n', ' ')
        subs.append({'start': start, 'end': end, 'text': text})
        
    return subs

def find_profanity_in_subs(subs, swear_list):
    """Identifies profane periods in subtitles."""
    profane_intervals = []
    
    # Pre-compile swear regex (word boundary to avoid partial matches)
    # Using the logic from utils/google_api but simpler for now
    clean_swears = [s.strip().lower() for s in swear_list if s.strip()]
    if not clean_swears:
        return []

    # Sort checks by length to catch phrases first? 
    # Actually simple word checking is often enough, but let's be careful.
    
    for sub in subs:
        text = sub['text'].lower()
        # Remove punctuation for checking (keep apostrophes to avoid he'll -> hell)
        text_clean = re.sub(r"[^\w\s']", '', text)
        words = text_clean.split()
        
        found = False
        for swear in clean_swears:
            # Check for exact phrase or word match
            # "god damn" in "god damn it"
            if f" {swear} " in f" {text_clean} ":
                 found = True
                 break
        
        if found:
            profane_intervals.append(sub)
            
    return profane_intervals

import statistics

def calculate_offset(words, subs):
    """
    Calculates the time offset between SRT and Transcription.
    Offset = SRT_Time - Transcription_Time
    """
    # Find potential anchors: distinct words with high confidence (>0.9) and length > 4
    anchors = []
    
    # Create word map for fast lookup? Or just iterate?
    # Transcription can be large.
    # Let's filter transcription for good candidates first.
    trans_candidates = [w for w in words if len(w['word']) > 4 and w.get('confidence', 0) > 0.9]
    
    if not trans_candidates:
        return 0.0

    # Limit to a subset to avoid O(N*M)
    # Pick 20 candidates distributed evenly
    step = max(1, len(trans_candidates) // 20)
    selected_trans = trans_candidates[::step]
    
    offsets = []
    
    for t_word in selected_trans:
        t_text = re.sub(r"[^\w\s']", '', t_word['word']).lower()
        t_start = t_word['start']
        
        # Search in subs
        # We need a sub that contains this word roughly near t_start
        # Search window +/- 5 seconds?
        for sub in subs:
            # Quick check on time
            # Assume offset isn't massive (e.g. < 60s)
            if abs(sub['start'] - t_start) > 60:
                continue
                
            s_text_clean = re.sub(r"[^\w\s']", '', sub['text']).lower()
            if t_text in s_text_clean.split():
                 # Found a match
                 # Calculate offset
                 # But subtitle start is for the whole line.
                 # This is tricky. A line might be "Hello world". "world" starts later than line start.
                 # But if we assume linear offset, we might just use the line start vs word start?
                 # Or better: median of diffs might handle the "word position in line" variance?
                 # "Word" start in transcription is precise.
                 # "Line" start in SRT is early.
                 # So SRT_start <= Word_Start (theoretically, if synched).
                 # Offset = SRT_Start - Word_Start. This will be negative usually (- (position in line)).
                 # This approach is flawed for "exact" offset.
                 
                 # Alternative: If a sub is ONLY one word?
                 if len(s_text_clean.split()) == 1:
                     diff = sub['start'] - t_start
                     offsets.append(diff)
                 else:
                     # Use the diff, knowing it includes "position in line" error.
                     # But if we take median, and lines vary in length, it might be messy.
                     # User suggested: "finding a bunch of sections that line up really well".
                     pass
    
    # If no single-word lines found, fall back to matching starts of lines?
    if not offsets:
         # new strategy: Find words that start lines?
         # If transcription word is "Hello" and Subtitle starts with "Hello".
         for sub in subs:
             if abs(sub['start'] - selected_trans[0]['start']) > 300: # optimization
                 continue
                 
             s_text_clean = re.sub(r"[^\w\s']", '', sub['text']).lower().split()
             if not s_text_clean: continue
             
             first_word = s_text_clean[0]
             
             # Find matching word in transcription near this sub start
             # (This is reverse of above loop)
             pass
    
    # Let's try a simpler approach for now:
    # Just take median of (Sub_Start - Word_Start) for matches.
    # It will slighty bias towards "earlier" (subtitle start), which is safer for muting (start mute earlier).
    # And since we assign FULL subtitle duration to the mute, this bias is acceptable.
    
    if not offsets:
         for t_word in selected_trans:
            t_text = re.sub(r"[^\w\s']", '', t_word['word']).lower()
            for sub in subs:
                if abs(sub['start'] - t_word['start']) > 10: continue
                s_words = re.sub(r"[^\w\s']", '', sub['text']).lower().split()
                if t_text in s_words:
                    offsets.append(sub['start'] - t_word['start'])
                    break 

    if offsets:
        return statistics.median(offsets)
    return 0.0

def inject_subtitles_into_words(csv_path, srt_path, output_path=None):
    """
    1. Load words from CSV.
    2. Load words from SRT.
    3. Calculate Offset.
    4. Find profanity in SRT.
    5. Check if that profanity exists in CSV words near that time (using offset).
    6. If not, insert it (using FULL subtitle duration).
    """
    
    swears = utils.parse_swears()
    clean_swears = [s.strip().lower() for s in swears if s.strip()]
    
    # Load subtitle exceptions — these words should NOT be injected from subtitles
    subtitle_exceptions = utils.parse_subtitle_exceptions()
    
    # Load CSV
    words = []
    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
             words.append({
                 "word": row["word"],
                 "start": float(row["start"]),
                 "end": float(row["end"]),
                 "confidence": float(row.get("confidence", 0.0))
             })
             
    # Parse SRT
    subs = parse_srt(srt_path)
    
    # Calculate Offset
    offset = calculate_offset(words, subs)
    print(f"Calculated offset (SRT - Trans): {offset:.3f}s")
    
    # Sort words by start time
    words.sort(key=lambda x: x['start'])
    
    print(f"Checking {len(subs)} subtitle lines against {len(words)} transcribed words.")

    inserted_count = 0
    unmatched_count = 0
    
    for sub in subs:
        sub_text = sub['text']
        sub_start = sub['start'] # Original SRT time
        sub_end = sub['end']
        
        # Adjusted time for comparison with transcription
        adj_start = sub_start - offset
        adj_end = sub_end - offset
        
        # 1. Identify swears in this subtitle block
        present_swears = []
        clean_sub_text = re.sub(r"[^\w\s']", '', sub_text).lower()
        
        for swear in clean_swears:
            # Skip exception words — these are allowed if they appear in subtitles
            if swear in subtitle_exceptions:
                continue
            # Match whole words/phrases
            if re.search(rf"\b{re.escape(swear)}\b", clean_sub_text):
                present_swears.append(swear)
        
        if not present_swears:
            continue
            
        # 2. Check coverage in transcription
        # Time window: Adjusted Sub Time +/- buffer
        buffer = 1.0 
        window_start = adj_start - buffer
        window_end = adj_end + buffer
        
        # Get transcription words in this window
        window_words = [w for w in words if w['end'] >= window_start and w['start'] <= window_end]
        
        for swear in present_swears:
            covered = False
            for w in window_words:
                w_text = re.sub(r"[^\w\s']", '', w['word']).lower()
                # strict check to avoid 'pass' matching 'ass'
                # but allow 'asshole' matching 'ass' if desired? 
                # Actually, if subtitle has 'ass', we want 'ass' or 'jackass' in transcription.
                # But NOT 'pass'.
                if re.search(rf"\b{re.escape(swear)}\b", w_text) or (len(swear) > 3 and swear in w_text):
                     covered = True
                     break
                
                # Fallback: if they are identical
                if w_text == swear:
                    covered = True
                    break
            
            if not covered:
                print(f"MISSING PROFANITY: '{swear}' in subtitle '{sub_text}' at {sub_start}-{sub_end} (Adj: {adj_start:.2f})")
                
                # INJECT with FULL SUBTITLE DURATION (Original SRT times)
                # Apply the offset back? No, mute list generation relies on "Word" times being relative to VIDEO.
                # SRT times are relative to VIDEO (usually). 
                # Transcription times are relative to VIDEO.
                # Only if they disagree (offset != 0) do we need to check coverage using offset.
                # But when we inject, we want the time to match the VIDEO.
                # If SRT matches Video, use SRT time.
                # If Transcription matches Video, and SRT is offset, we should probably correct SRT time?
                # Usually SRT is "True" for text content, but simple offset might handle sync issues.
                # User says: "finding a bunch of sections that line up really well".
                # If we assume SRT is correct for the audio it represents:
                # We should inject at SRT time?
                # But if offset is -2s (SRT is early), and we inject at SRT time, we mute early.
                # Correct.
                # Wait, if `offset = SRT - Trans`. `Trans = SRT - offset`.
                # If Trans is "True" (aligned to video by Google), then `SRT = Trans + offset`.
                # If `offset` is non-zero, it means SRT is shifted relative to google output.
                # If we rely on Google timestamps for existing words, we should rely on SRT time MINUS offset for injected words?
                # so that they align with the Google timeline (which aligns with video)?
                # Or does SRT align with video and Google is wrong? 
                # Usually Google is very accurate to audio. SRT might be from a different release (offset).
                # So we should Shift Injected Word to match Google's Timeline.
                # Adjusted Time = SRT_Time - offset.
                
                final_start = sub_start - offset
                final_end = sub_end - offset
                
                new_word = {
                    "word": swear,
                    "start": final_start,
                    "end": final_end,
                    "confidence": 1.0
                }
                words.append(new_word)
                inserted_count += 1
                
    if inserted_count > 0:
        words.sort(key=lambda x: x['start'])
        if output_path is None:
            p = Path(csv_path)
            output_path = p.parent / (p.stem + "_aligned.csv")
            
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ["start", "end", "word", "confidence"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for w in words:
                row = {k: w.get(k, "") for k in fieldnames}
                writer.writerow(row)
        print(f"Injected {inserted_count} words. Saved to {output_path}")
        return output_path
    else:
        print("No missing profanity found via subtitle alignment.")
        return None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Inject profanity from subtitles into transcription CSV.")
    parser.add_argument("csv", help="Path to transcription CSV (e.g. video_name_words.csv)")
    parser.add_argument("srt", help="Path to subtitle file (e.g. video_name.srt)")
    parser.add_argument("--output", "-o", help="Optional output path for aligned CSV")
    parser.add_argument("--encoding", default="utf-8", help="Encoding for SRT file (default: utf-8)")
    
    args = parser.parse_args()
    
    if not Path(args.csv).exists():
        logger.error(f"CSV file not found: {args.csv}")
        exit(1)
    if not Path(args.srt).exists():
        logger.error(f"SRT file not found: {args.srt}")
        exit(1)
        
    inject_subtitles_into_words(args.csv, args.srt, output_path=args.output)
