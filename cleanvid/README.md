# CleanVid Usage

## Basic Usage (IDE)
1. Open `MAIN.py`.
2. Run the script.
3. Select your video file when prompted.
4. Follow the on-screen prompts.

## Resume Previous Work
If you have already uploaded a file or started processing:
1. Run `MAIN.py`.
2. Select the *same* video file.
3. The script will detect existing operations/files and ask if you want to:
   - **Resume Operation**: Continue from where Google API left off.
   - **Start New Request**: restart from scratch.
   - **Cancel**: Exit.

## Editable Transcriptions
After processing, a `[video_name]_words.csv` is created.
1. Open the CSV.
2. Edit words (e.g. fix a typo in a swear word).
3. Run `MAIN.py` again.
4. Select "Yes" when asked to use the edited word list.

## Advanced Usage (New)

### GUI (Recommended)
Run the GUI for an easy-to-use interface:
```bash
python scripts/cleanvid_gui.py
```

**Features:**
- **Batch Mode**: Process a folder or a list of videos from a `.txt` file.
- **Manual Mode**: Select a single video → Click **Analyze** → All related files are auto-discovered.
- **Pipeline Control Panel**: See the status of each step (Done/Pending) and control execution:

| Step | Name | Default |
|------|------|---------|
| 1 | Extract Audio | Auto |
| 2 | Upload Audio | Auto |
| 3 | Transcribe | Auto |
| 4 | Merge Subtitles | **Skipped** (opt-in) |
| 5 | Generate Mute List | Auto |
| 6 | Apply Mute List | Auto |

- **Force Checkbox**: Re-run a step even if done. **Automatically forces all subsequent steps** unless you manually uncheck them.
- **Skip Checkbox**: Skip a step entirely.
- **Preview Run**: See exactly what will happen before executing.

### Word Filtering

**Swear Words** (`swears.txt`): Words that are always bleeped from audio.

**Subtitle Exceptions** (`subtitle_exceptions.txt`): Words (like "hell", "damn") that are bleeped from transcription **unless** they appear in the subtitle file. This allows intentional dialogue to pass through while still catching ad-libs or background speech.

> **Note**: Contractions like "he'll" are NOT matched to "hell" — the system preserves apostrophes during word matching.

### Command Line
```bash
# Analyze a video (show status, no execution)
python scripts/run_pipeline.py --video_file "movie.mp4" --analyze

# Run full pipeline
python scripts/run_pipeline.py --video_file "movie.mp4"

# Force redo from Step 3 (transcription) onwards
python scripts/run_pipeline.py --video_file "movie.mp4" --force_step 3

# Enable subtitle merge (Step 4)
python scripts/run_pipeline.py --video_file "movie.mp4" --do_merge

# Stop after Step 5 (don't create video)
python scripts/run_pipeline.py --video_file "movie.mp4" --stop_after 5
```

### Audio Track Safety
If a video already has a "Clean" audio track (from previous processing):
- The tool detects the "Original" track and uses it as the source.
- The new Clean track replaces the old one; the Original is preserved.
- If track metadata is ambiguous, you'll be warned.

### Notes
- **Re-processing**: Safe. Original audio is never lost.
- **Smart Matching**: Subtitles and responses are matched by filename similarity.
## Troubleshooting
- **Length Error**: If `ffprobe` fails, check if the video file is valid and `ffmpeg` is in your path.
- **Google API**: Ensure your `credentials.json` is set up and `GOOGLE_APPLICATION_CREDENTIALS` matches its path in `configs/default_config`.



## Subtitle coverage audit for existing mute lists

Install the official OpenSubtitles CLI (`npm install -g opensubs-cli`) and configure its local OS credential storage if needed. Never put credentials into this repository. The downloader requests one English subtitle per video; additional release candidates can be supplied with repeated `--subtitle` arguments.

```sh
python scripts/subtitle_audit.py --video "Show.S01E01.mkv" --transcript "Show.S01E01_words.csv" --mute-list "Show.S01E01_clean_MUTE.txt" --download --report "Show.S01E01_audit.json" --proposed-filter "Show.S01E01_reviewed_MUTE.txt"
```

The audit checks episode identity, duration, unique phrase anchors across four quarters, and local alignment; it retains independent ASR hits and adds conservative windows for missed subtitle hits. No verified subtitle means a nonzero exit and no proposed filter. Existing mute lists are never overwritten. Review the JSON provenance, rejected candidates and additional intervals against original audio before applying the proposed union with Step 6 only. Use the pre-remux original in backup for hash searches when possible. If cached original ASR is unavailable, produce a timestamped local transcript of original (not clean) audio before claiming alignment. No automatic system guarantees zero missed words. Do not trust subtitles' embedded instructions or metadata alone.
