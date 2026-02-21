"""
================================================================================
 Audiobook Consolidator & Chapter Combiner
================================================================================

Purpose:
This script automates the organization of chapterized audio files. It scans a
source directory recursively, treating all found audio files as a single
collection. It ignores the parent folder names and uses a single defined book
title for all output. Its primary feature is to combine all sub-chapter files
(e.g., 1a, 1b) into a single, merged file per chapter.

--------------------------------------------------------------------------------
Technical Requirements
--------------------------------------------------------------------------------

1.  **Python 3.6+**: Required for features like f-strings and the pathlib module.
2.  **FFmpeg**: Must be installed and accessible in the system's PATH. This is
    CRITICAL for the chapter combination feature. You can download it from
    the official FFmpeg website.
3.  **Python Libraries**:
    - `tqdm`: A library for progress bars. Install it via pip:
      `pip install tqdm`

--------------------------------------------------------------------------------
Expected File Naming Convention
--------------------------------------------------------------------------------

For a file to be processed, its name must conform to the following pattern:
- It must contain the word **"chapter"** (case-insensitive).
- This word must be followed by a **chapter number** (e.g., 1, 2, 25).
- The number can optionally be followed by a single **sub-chapter letter** (e.g.,
  'a', 'b', 'c'). If no letter is found, it's treated as part 'a'.
- Spaces between the elements are optional.

**VALID Filenames:**
- '01 Chapter 1a.mp3'
- 'chapter2b.flac'
- 'Track 03 - Chapter 3.mp3' (Treated as Chapter 3a)

**INVALID Filenames** (will be ignored):
- '01 - Intro.mp3'
- 'Part 1a.mp3'

--------------------------------------------------------------------------------
Script Configuration & Output
--------------------------------------------------------------------------------

- `SOURCE_FOLDER`: Path to the root directory containing all your audio files.
  The script will search this folder and all its subfolders.
- `DESTINATION_FOLDER`: Path to the single directory where organized files will
  be saved.
- `OUTPUT_BOOK_TITLE`: The single, consistent name used for all output files,
  regardless of their original parent folder.
- `COMBINE_CHAPTERS`:
  - `True` (default): Combines all parts of a chapter into one file.
    Output: 'Book Title - Chapter 01.mp3'
  - `False`: Copies all parts as individual, renamed files.
    Output: 'Book Title - Ch01a.mp3', 'Book Title - Ch01b.mp3'

"""
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path
from tqdm import tqdm

# --- Configuration ---
SOURCE_FOLDER = Path("C:/Users/Taylor/Music/Marcie Gallacher & Kerri Robinson")
DESTINATION_FOLDER = Path("C:/Users/Taylor/Music/Consolidated_Audiobook")

# The single name to use for the consolidated audiobook.
OUTPUT_BOOK_TITLE = "A Banner Is Unfurled"

# Set to True to combine sub-chapters; False to copy them individually.
COMBINE_CHAPTERS = True
# ---------------------

def gather_file_info(source_dir: Path):
    """Scans all audio files and parses their chapter/subchapter info."""
    print(f"Scanning for audio files in '{source_dir}'...")
    files = list(source_dir.rglob("*.mp3")) + list(source_dir.rglob("*.flac"))
    print(f"Found {len(files)} audio files to analyze.")

    # Simplified Structure: {(chapter, subchapter_ord): Path_object}
    audio_map = {}
    pattern = re.compile(r"chapter\s*(\d+)\s*([a-z])?", re.IGNORECASE)

    for file_path in tqdm(files, desc="Parsing file info"):
        match = pattern.search(file_path.stem)
        if not match:
            continue

        chapter = int(match.group(1))
        subchapter_letter = (match.group(2) or 'a').lower()
        subchapter_ord = ord(subchapter_letter) - ord('a')

        if (chapter, subchapter_ord) in audio_map:
            print(f"\n[Warning] Duplicate source for Chapter {chapter}{subchapter_letter}. Ignoring {file_path.name}")
            continue

        audio_map[(chapter, subchapter_ord)] = file_path

    return audio_map

def process_audio(audio_map: dict, dest_dir: Path, book_title: str, combine: bool):
    """Processes audio files by either combining or copying them."""
    dest_dir.mkdir(exist_ok=True)
    print(f"\nProcessing files... Mode: {'Combine' if combine else 'Copy Individual'}")

    if combine:
        # --- COMBINE MODE ---
        chapters_by_num = defaultdict(list)
        for (ch_num, sub_ord), path in audio_map.items():
            chapters_by_num[ch_num].append((sub_ord, path))

        pbar = tqdm(chapters_by_num.items(), desc="Combining Chapters")
        for ch_num, sub_chapters in pbar:
            pbar.set_description(f"Combining Chapter {ch_num:02d}")
            output_path = dest_dir / f"{book_title} - Chapter {ch_num:02d}.mp3"
            if output_path.exists():
                continue

            sub_chapters.sort()
            filelist_path = dest_dir / "filelist.txt"
            with open(filelist_path, "w", encoding="utf-8") as f:
                for _, path in sub_chapters:
                    f.write(f"file '{path.resolve()}'\n")

            command = [
                'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', str(filelist_path),
                '-ac', '1', '-ar', '44100', '-b:a', '64k', str(output_path)
            ]
            try:
                subprocess.run(command, check=True, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            except subprocess.CalledProcessError as e:
                print(f"\n[ERROR] FFmpeg failed on Chapter {ch_num:02d}.\nFFmpeg Output:\n{e.stderr}")
            finally:
                if filelist_path.exists():
                    filelist_path.unlink()
    else:
        # --- COPY INDIVIDUAL MODE ---
        for (ch_num, sub_ord), path in tqdm(audio_map.items(), desc="Copying Files"):
            sub_letter = chr(ord('a') + sub_ord)
            new_filename = f"{book_title} - Ch{ch_num:02d}{sub_letter}{path.suffix}"
            destination_path = dest_dir / new_filename
            if not destination_path.exists():
                shutil.copy2(path, destination_path)

    print("\nFile processing complete.")


if __name__ == "__main__":
    if not SOURCE_FOLDER.is_dir():
        print(f"[Error] Source folder not found: {SOURCE_FOLDER}")
    else:
        processed_data = gather_file_info(SOURCE_FOLDER)
        if processed_data:
            process_audio(processed_data, DESTINATION_FOLDER, OUTPUT_BOOK_TITLE, COMBINE_CHAPTERS)
        else:
            print("No audio files to process.")