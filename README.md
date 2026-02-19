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

