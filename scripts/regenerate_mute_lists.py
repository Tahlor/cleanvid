import sys
import os
from pathlib import Path
import argparse
import glob
import re
import difflib

# Add root directory to sys.path
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

import utils
import google_api
import Global_Config
from scripts import align_subtitles

def parse_filename(name):
    """
    Extracts (title_slug, season, episode) from filename.
    Returns (cleaned_title, s, e) or (cleaned_title, None, None).
    """
    # Normalize: lower, replace dots/underscores with spaces
    name = name.lower()
    
    # Check for SxxExx pattern
    match = re.search(r'(.+?)[ ._-]+s(\d+)[ ._-]*e(\d+)', name)
    if match:
        title = match.group(1)
        s = int(match.group(2))
        e = int(match.group(3))
        # Clean title
        title = re.sub(r'[^\w]', '', title)
        return (title, s, e)
    
    # Fallback: just clean stem
    # Remove year if present (e.g. 1999)
    # Be careful not to remove "2001" from "2001 A Space Odyssey" if it's the title?
    # Usually matches are safe if we strip parens and years.
    clean = re.sub(r'[^\w]', '', name)
    return (clean, None, None)

def build_video_index(root_paths):
    """
    Scans root paths for video files and returns a dict: {key: full_path}
    Keys can be:
      - (title, s, e) tuple
      - simple_stem string
    """
    video_extensions = {".mp4", ".mkv", ".avi", ".m4v", ".mov"}
    index = {}
    print("Building video index...")
    for root in root_paths:
        p = Path(root)
        if not p.exists():
            print(f"Warning: path {root} does not exist")
            continue
            
        for f in p.rglob("*"):
            if f.is_file() and f.suffix.lower() in video_extensions:
                # 1. Store by exact stem (backup)
                index[f.stem] = f
                
                # 2. Store by parsed info
                parsed = parse_filename(f.stem)
                if parsed not in index:
                    index[parsed] = f
                else:
                    # Duplicate handling?
                    # Verify if duplicate is same file?
                    pass
                    
    print(f"Indexed {len(index)} keys.")
    return index

def process_responses(response_folder, video_index):
    """
    Iterates response files, finds matching video, checks for SRT, aligns, regenerates mute list.
    """
    p = Path(response_folder)
    
    # We prioritize response files (raw API output)
    files = list(p.glob("*.response"))
    # Also check pickle if no response found? 
    # For now iterate responses as primary source.
    
    credential_path = Global_Config.GCS_CREDENTIALS_PATH
    speech_api = google_api.google_speech_api(credential_path=credential_path)
    
    for f in files:
        stem = f.stem
        # Clean stem from timestamp
        # e.g. "Video.Name_2023-01-01..."
        safe_stem = re.sub(r'_\d{4}-\d{2}-\d{2}.*', '', stem)
        
        # Try to find video
        video_path = None
        
        # 1. Try exact stem match in index (if index has simple string keys)
        if safe_stem in video_index:
            video_path = video_index[safe_stem]
            
        # 2. Try parsed match
        if not video_path:
            parsed = parse_filename(safe_stem)
            if parsed in video_index:
                video_path = video_index[parsed]
                
        if not video_path:
            # print(f"Skipping {f.name}: Video not found in index.")
            # Be less noisy?
            continue

        print(f"\nProcessing: {video_path.name}")
            
        # Check for SRT
        srt_path = None
        # Logic to find SRT near video
        # Priority: .srt.bak, .srt
        # Logic: exact match or "contains stem" match?
        
        # Strict check first
        for ext in [".srt.bak", ".srt"]:
            check = video_path.with_suffix(ext)
            if check.exists():
                srt_path = check
                break
                
        # Loose check in folder
        if not srt_path:
            # e.g. "Video.Name.1.en.bak"
            # Find files starting with relevant part of stem?
            # Or just any .srt/.bak in folder? 
            # If multiple, careful.
            candidates = list(video_path.parent.glob("*.bak")) + list(video_path.parent.glob("*.srt"))
            # Filter by stem overlap?
            # If 'The Right Stuff' is in filename?
            
            best_score = 0
            best_cand = None
            
            for c in candidates:
                # simple similarity
                ratio = difflib.SequenceMatcher(None, video_path.stem, c.stem).ratio()
                if ratio > 0.5 and ratio > best_score:
                    best_score = ratio
                    best_cand = c
            
            if best_cand:
                srt_path = best_cand
        
        words = []
        try:
            response_obj = speech_api.load_response(f)
            words = speech_api.get_words_from_response(response_obj)
        except Exception as e:
            print(f"Failed to load words from {f}: {e}")
            continue

        if not words:
            print("No words extracted.")
            continue

        # Save base CSV to RESPONSE FOLDER (standardize location)
        csv_path = p / (safe_stem + "_words.csv")
        speech_api.save_words_to_csv(words, csv_path)
            
        aligned_csv = None
        if srt_path:
            print(f"Found SRT: {srt_path.name}")
            aligned_csv = align_subtitles.inject_subtitles_into_words(str(csv_path), str(srt_path))
        
        if aligned_csv:
             # Reload words from aligned CSV for mute list generation
             words = speech_api.load_words_from_csv(aligned_csv)
        
        # Generate Mute List
        print("Generating Mute List...")
        mute_list, transcript, _ = speech_api.create_mute_list_from_words(words)
        
        # Save Mute List
        final_mute_list = utils.create_mute_list(mute_list)
        mute_list_path = video_path.parent / (video_path.stem + "_clean_MUTE.txt")
        utils.format_mute_list(final_mute_list, mute_list_path)
        print(f"Saved: {mute_list_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch regenerate mute lists using local SRTs.")
    parser.add_argument("--roots", nargs="+", help="Root directories to scan for videos", required=True)
    parser.add_argument("--responses", help="Folder containing response files", default="./data/google_api")
    
    args = parser.parse_args()
    
    index = build_video_index(args.roots)
    process_responses(args.responses, index)
