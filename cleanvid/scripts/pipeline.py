"""
CleanVid Pipeline Orchestrator

Defines the 6-step pipeline and provides orchestration logic for:
- Status detection (what's already done)
- Force/Skip/Cascade control
- Audio track safety
- Subtitle merge validation
"""

import sys
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable
from enum import Enum
import difflib
from concurrent.futures import ThreadPoolExecutor

# Add root directory to sys.path
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

import utils
import google_api
import Global_Config
import utilization


class StepStatus(Enum):
    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
    ERROR = "error"
    RUNNING = "running"


@dataclass
class PipelineStep:
    """Represents a single pipeline step."""
    number: int
    name: str
    description: str
    check_done: Callable  # Function to check if step is already done
    execute: Callable     # Function to execute the step
    status: StepStatus = StepStatus.PENDING
    force: bool = False
    skip: bool = False
    opt_in: bool = False  # If True, skipped by default (must explicitly enable)
    output_path: Optional[Path] = None
    error_message: Optional[str] = None


@dataclass
class PipelineContext:
    """Holds all paths and state for a single video's pipeline run."""
    video_path: Path
    
    # Derived paths (auto-populated)
    audio_path: Optional[Path] = None
    gcs_uri: Optional[str] = None
    operation_path: Optional[Path] = None  # Outstanding transcription operation
    response_path: Optional[Path] = None
    subtitle_path: Optional[Path] = None
    csv_path: Optional[Path] = None
    mute_list_path: Optional[Path] = None
    clean_video_path: Optional[Path] = None
    
    # Config
    response_folder: Path = field(default_factory=lambda: Path("./data/google_api"))
    
    # Audio track info
    audio_track_count: int = 1
    original_track_index: int = 0  # Which track is the "Original"
    audio_track_warning: Optional[str] = None
    
    # Subtitle merge info
    subtitle_match_confidence: float = 0.0
    merge_coverage_score: float = 0.0
    unmatched_profanities: List[str] = field(default_factory=list)
    
    # Video info (for utilization tracking)
    video_duration_seconds: float = 0.0


class Pipeline:
    """Orchestrates the 6-step video cleaning pipeline."""
    
    STEP_NAMES = [
        "Extract Audio",
        "Upload Audio",
        "Transcribe",
        "Merge Subtitles",
        "Generate Mute List",
        "Apply Mute List"
    ]
    
    def __init__(self, context: PipelineContext):
        self.context = context
        self.steps: List[PipelineStep] = []
        self.speech_api = None
        self._init_steps()
        
    def _init_steps(self):
        """Initialize the 6 pipeline steps."""
        self.steps = [
            PipelineStep(
                number=1,
                name="Extract Audio",
                description="Extract audio track from video to FLAC",
                check_done=self._check_audio_exists,
                execute=self._execute_extract_audio,
            ),
            PipelineStep(
                number=2,
                name="Upload Audio",
                description="Upload audio file to Google Cloud Storage",
                check_done=self._check_uploaded,
                execute=self._execute_upload,
            ),
            PipelineStep(
                number=3,
                name="Transcribe",
                description="Transcribe audio via Google Speech API",
                check_done=self._check_transcribed,
                execute=self._execute_transcribe,
            ),
            PipelineStep(
                number=4,
                name="Merge Subtitles",
                description="Align subtitle profanity with transcription",
                check_done=self._check_merged,
                execute=self._execute_merge,
                opt_in=True,  # Skipped by default
                skip=True,    # Default to skip
            ),
            PipelineStep(
                number=5,
                name="Generate Mute List",
                description="Create mute list from words",
                check_done=self._check_mute_list_exists,
                execute=self._execute_generate_mute_list,
            ),
            PipelineStep(
                number=6,
                name="Apply Mute List",
                description="Create clean video with muted audio",
                check_done=self._check_clean_video_exists,
                execute=self._execute_apply_mute_list,
            ),
        ]
        
    def _get_speech_api(self):
        if not self.speech_api:
            self.speech_api = google_api.google_speech_api(
                credential_path=Global_Config.GCS_CREDENTIALS_PATH,
                api="video",  # Video Intelligence API (all operations use this)
                require_api_confirmation=False,  # Pipeline runs in background thread
            )
        return self.speech_api
    
    # --- Path Discovery ---
    
    def discover_paths(self):
        """Auto-populate all paths based on video_path."""
        v = self.context.video_path
        
        # Audio (segments are extracted to ./temp/{stem}/ directory)
        self.context.audio_path = Path(f"./temp/{v.stem}")
        
        # Populate GCS URIs if audio segments exist (robustness for Step 3)
        if self.context.audio_path.exists():
             segments = sorted(self.context.audio_path.glob("*.flac"))
             if segments:
                 uris = [utils.generate_gcs_uri(str(s)) for s in segments]
                 self.context.gcs_uri = uris[0] if len(uris) == 1 else uris
        
        # Response (search in response_folder)
        self.context.response_path = self._find_response_file()
        
        # Operation file (outstanding transcription)
        self.context.operation_path = self._find_operation_file()
        
        # Subtitle (search near video)
        self.context.subtitle_path, self.context.subtitle_match_confidence = self._find_subtitle_file()
        
        # CSV (derived from video stem in response folder)
        # Check for latest version
        base_csv = self.context.response_folder / f"{v.stem}_words.csv"
        self.context.csv_path = self._find_latest_csv(base_csv)
        
        # Mute list (in video directory)
        self.context.mute_list_path = v.parent / f"{v.stem}_clean_MUTE.txt"
        
        # Clean video
        self.context.clean_video_path = v.parent / f"{v.stem}_clean{v.suffix}"
        
        # Audio track analysis
        self._analyze_audio_tracks()
        
        # Get video duration for utilization tracking
        try:
            self.context.video_duration_seconds = utils.get_length(
                self.context.video_path, "ffprobe"
            )
        except:
            self.context.video_duration_seconds = 0
        
    def _find_response_file(self) -> Optional[Path]:
        """Find matching response file in response_folder."""
        return self._find_api_file(".response")
    
    def _find_operation_file(self) -> Optional[Path]:
        """Find matching operation file in response_folder (outstanding transcription)."""
        return self._find_api_file(".operation")
    
    def _find_api_file(self, extension: str) -> Optional[Path]:
        """Find matching file by extension (.response or .operation) in response_folder."""
        from scripts.regenerate_mute_lists import parse_filename
        
        target_stem = self.context.video_path.stem
        target_parsed = parse_filename(target_stem)
        
        p = self.context.response_folder
        if not p.exists():
            return None
            
        import re
        for f in p.glob(f"*{extension}"):
            stem = f.stem
            safe_stem = re.sub(r'_\d{4}-\d{2}-\d{2}.*', '', stem.replace(extension, "").replace("_words", ""))
            
            if safe_stem == target_stem:
                return f
            if parse_filename(safe_stem) == target_parsed:
                return f
        return None
        
    def _find_subtitle_file(self) -> tuple[Optional[Path], float]:
        """Find matching subtitle file near video."""
        v = self.context.video_path
        
        # Strict check
        for ext in [".srt.bak", ".srt"]:
            check = v.with_suffix(ext)
            if check.exists():
                return check, 1.0
        
        # Loose check
        candidates = list(v.parent.glob("*.bak")) + list(v.parent.glob("*.srt"))
        best_score = 0.0
        best_cand = None
        
        for c in candidates:
            ratio = difflib.SequenceMatcher(None, v.stem, c.stem).ratio()
            if ratio > best_score:
                best_score = ratio
                best_cand = c
                
        return best_cand, best_score
        
    def _find_latest_csv(self, base_path: Path) -> Path:
        """Find the latest version of the CSV file."""
        if not base_path.exists():
            return base_path
            
        # Check for _v{n} versions
        # Pattern: {stem}_words_v{n}.csv
        # or just {stem}_v{n}.csv if base is {stem}.csv? 
        # Implementation: Check base, then check v2, v3...
        # Actually easier: glob for pattern
        
        # Assume base is "..._words.csv"
        stem = base_path.stem # video_words
        parent = base_path.parent
        suffix = base_path.suffix
        
        latest = base_path
        highest_v = 1
        
        # Check explicit versions
        # Glob for "{stem}_v*{suffix}"
        # But our base usually ends in "_words". 
        # Let's support appending _vN to the stem.
        
        for p in parent.glob(f"{stem}_v*{suffix}"):
            # extract version
            try:
                # expecting ..._words_v2.csv
                v_str = p.stem.rsplit("_v", 1)[1]
                v = int(v_str)
                if v > highest_v:
                    highest_v = v
                    latest = p
            except:
                continue
                
        return latest
        
    def _analyze_audio_tracks(self):
        """Check audio tracks for safety."""
        try:
            ffprobe_json = utils.get_ffprobe_json(self.context.video_path)
            streams = ffprobe_json.get("streams", [])
            audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
            
            self.context.audio_track_count = len(audio_streams)
            
            if len(audio_streams) >= 2:
                # Look for "Original" title
                for i, s in enumerate(audio_streams):
                    tags = s.get("tags", {})
                    title = tags.get("title", "").lower()
                    if "original" in title:
                        self.context.original_track_index = i
                        return
                
                # No explicit "Original" found - warn user
                self.context.audio_track_warning = (
                    f"Video has {len(audio_streams)} audio tracks but no 'Original' title found. "
                    "Assuming Track 1 is original. Please verify."
                )
                self.context.original_track_index = 1  # Assume second track
            else:
                self.context.original_track_index = 0
                
        except Exception as e:
            self.context.audio_track_warning = f"Could not analyze audio tracks: {e}"
    
    # --- Status Checks ---
    
    def _check_audio_exists(self) -> bool:
        if not self.context.audio_path or not self.context.audio_path.exists():
            return False
        return any(self.context.audio_path.glob("*.flac"))
        
    def _check_uploaded(self) -> bool:
        # Check if file exists in GCS bucket
        # For now, we check if response exists (implies upload happened)
        return self._check_transcribed()  # Simplified
        
    def _check_transcribed(self) -> bool:
        return self.context.response_path and self.context.response_path.exists()
        
    def _check_merged(self) -> bool:
        return self.context.csv_path and self.context.csv_path.exists()
        
    def _check_mute_list_exists(self) -> bool:
        return self.context.mute_list_path and self.context.mute_list_path.exists()
        
    def _check_clean_video_exists(self) -> bool:
        return self.context.clean_video_path and self.context.clean_video_path.exists()
    
    # --- Execution ---
    
    def _execute_extract_audio(self):
        print(f"  Extracting audio from {self.context.video_path.name}...")
        utils.split_audio(
            self.context.video_path,
            codec="flac",
            normalize_audio=False,
            name=self.context.video_path.stem
        )
        # Move from temp to expected location if needed
        
    def _execute_upload(self):
        api = self._get_speech_api()
        audio_dir = self.context.audio_path
        segments = sorted(audio_dir.glob("*.flac"))
        if not segments:
            raise FileNotFoundError(f"No .flac segments found in {audio_dir}")
        
        if len(segments) == 1:
            # Single segment — no threading needed
            print(f"  Uploading {segments[0].name} to GCS...")
            uri = api.upload_file(str(segments[0]))
            self.context.gcs_uri = uri
            return
        
        # Multiple segments — upload in parallel
        print(f"  Uploading {len(segments)} segments in parallel...")
        
        def upload_one(seg):
            print(f"  Uploading {seg.name} to GCS...")
            return api.upload_file(str(seg))
        
        with ThreadPoolExecutor(max_workers=len(segments)) as executor:
            gcs_uris = list(executor.map(upload_one, segments))
        
        self.context.gcs_uri = gcs_uris
        
    def _execute_transcribe(self):
        """Transcribe audio via Google Speech API.
        
        Three scenarios:
        1. Response file exists -> already done (handled by check_done, shouldn't reach here)
        2. Operation file exists -> resume polling (no new API call, no credit charge)
        3. Neither exists -> submit new transcription (costs credits)
        
        For multiple segments, all operations are submitted first, then polled
        concurrently. Results are merged into a single combined words CSV.
        """
        api = self._get_speech_api()
        name = self.context.video_path.stem
        
        # Scenario 2: Resume outstanding operation
        if self.context.operation_path and self.context.operation_path.exists():
            print(f"  Resuming outstanding operation: {self.context.operation_path.name}")
            operation = api.restore_operation(self.context.operation_path)
            response = api.get_response(operation=operation, name=name)
            # Update context with new response path
            self.context.response_path = self._find_response_file()
            if not self.context.response_path:
                raise RuntimeError("Operation completed but no response file was saved.")
            print(f"  Transcription resumed successfully: {self.context.response_path.name}")
            return
        
        # Scenario 3: New transcription request
        print(f"  Submitting new transcription request...")
        
        # Check utilization limit BEFORE submitting
        if utilization.is_over_limit():
            raise RuntimeError(
                f"Monthly credit limit exceeded! {utilization.get_usage_summary()}"
            )
        
        # Verify we have audio uploaded (GCS URI)
        if not self.context.gcs_uri:
            raise RuntimeError("No GCS URI found. Upload step may have failed.")
        
        gcs_uri = self.context.gcs_uri
        
        if isinstance(gcs_uri, list) and len(gcs_uri) > 1:
            # Multiple segments — submit all, then poll all concurrently
            print(f"  Submitting {len(gcs_uri)} segments in parallel...")
            operations = []
            for uri in gcs_uri:
                seg_name = Path(uri).stem  # Use segment filename to avoid collisions
                print(f"    Submitting {seg_name}...")
                op, op_name = api.submit_operation(storage_uri=uri, name=seg_name)
                operations.append((op, op_name))
            
            print(f"  All {len(operations)} operations submitted. Polling concurrently...")
            results = api.poll_all_operations(operations)
            
            # Merge words from all segments into one combined list
            all_words = []
            for response, seg_name in results:
                words = api.get_words_from_response(response)
                all_words.extend(words)
                # Save per-segment CSV too
                seg_csv = api.response_output_folder / f"{seg_name}_words.csv"
                api.save_words_to_csv(words, seg_csv)
                print(f"  Exported segment words to {seg_csv}")
            
            # Sort combined words by start time (segments may overlap slightly)
            all_words.sort(key=lambda w: w["start"])
            
            # Save combined CSV
            combined_csv = api.response_output_folder / f"{name}_words.csv"
            api.save_words_to_csv(all_words, combined_csv)
            print(f"  Exported combined words to {combined_csv}")
            
            # Use the last segment's response file for downstream compatibility
            self.context.response_path = self._find_response_file()
        else:
            # Single segment — use existing process_speech (blocking but simple)
            uri = gcs_uri[0] if isinstance(gcs_uri, list) else gcs_uri
            api.process_speech(storage_uri=uri, name=name)
            self.context.response_path = self._find_response_file()
        
        # Track utilization ONLY after successful submission
        if self.context.video_duration_seconds > 0:
            utilization.add_usage(
                self.context.video_path.name,
                self.context.video_duration_seconds
            )
        
        if not self.context.response_path:
            raise RuntimeError("Transcription completed but no response file was saved.")
        
    def _execute_merge(self):
        print(f"  Merging subtitles...")
        from scripts import align_subtitles
        
        if not self.context.subtitle_path:
            raise ValueError("No subtitle file found for merge.")
            
        # Load words from response
        api = self._get_speech_api()
        if not self.context.response_path:
             raise ValueError("No response file found. Transcribe step may have failed or was skipped.")
        response_obj = api.load_response(self.context.response_path)
        words = api.get_words_from_response(response_obj)
        
        # Save base CSV
        base_csv = self.context.response_folder / f"{self.context.video_path.stem}_words_base.csv"
        api.save_words_to_csv(words, base_csv)
        
        # Align
        # align_subtitles opens base_csv and writes to aligned_csv
        aligned_csv = align_subtitles.inject_subtitles_into_words(
            str(base_csv),
            str(self.context.subtitle_path)
        )
        
        if aligned_csv:
            # Move to final location
            target = self.context.csv_path
            
            # Retry logic for moving file
            import time
            max_retries = 3
            for i in range(max_retries):
                try:
                    if target.exists():
                        target.unlink() # Explicitly remove target first
                    Path(aligned_csv).replace(target)
                    break
                except (PermissionError, OSError) as e:
                    if i == max_retries - 1:
                        print(f"  Warning: Could not write to {target} ({e}). Creating new version...")
                        
                        # Determine new version
                        stem = target.stem
                        parent = target.parent
                        suffix = target.suffix
                        
                        if "_v" in stem and stem.rsplit("_v", 1)[1].isdigit():
                            base, v_str = stem.rsplit("_v", 1)
                            new_v = int(v_str) + 1
                            new_name = f"{base}_v{new_v}{suffix}"
                        else:
                            new_name = f"{stem}_v2{suffix}"
                            
                        new_target = parent / new_name
                        print(f"  New target: {new_target}")
                        
                        Path(aligned_csv).replace(new_target)
                        
                        # CRITICAL: Update context so next steps use the new file
                        self.context.csv_path = new_target
                    else:
                        print(f"  File access error, retrying ({i+1}/{max_retries})...")
                        time.sleep(1.0)
            
    def _execute_generate_mute_list(self):
        print(f"  Generating mute list...")
        api = self._get_speech_api()
        
        # Load words from CSV if exists, else from response
        if self.context.csv_path and self.context.csv_path.exists():
            words = api.load_words_from_csv(self.context.csv_path)
        else:
            if not self.context.response_path:
                raise ValueError("No response file or CSV found. Cannot generate mute list.")
            response_obj = api.load_response(self.context.response_path)
            words = api.get_words_from_response(response_obj)
            
        mute_list, _, mute_details = api.create_mute_list_from_words(words)
        final_mute_list = utils.create_mute_list(mute_list)
        utils.format_mute_list(final_mute_list, self.context.mute_list_path)
        
        # Save human-readable report next to movie
        report_path = self.context.video_path.parent / f"{self.context.video_path.stem}_clean_REPORT.txt"
        self._save_mute_report(mute_details, report_path)
        
    @staticmethod
    def _save_mute_report(mute_details, report_path):
        """Save human-readable mute report with timestamps and censored words."""
        def fmt(seconds):
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = seconds % 60
            return f"{h:02d}:{m:02d}:{s:05.2f}"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            for start, end, word in mute_details:
                f.write(f"{fmt(start)} - {fmt(end)}  {word}\n")
        print(f"  Saved mute report to {report_path}")
        
    def _execute_apply_mute_list(self):
        print(f"  Applying mute list to create clean video...")
        utils.create_clean_video(
            str(self.context.video_path),
            str(self.context.clean_video_path),
            mute_list_file=self.context.mute_list_path
        )
    
    # --- Orchestration ---
    
    def detect_status(self):
        """Check each step's status based on existing outputs."""
        for step in self.steps:
            step.error_message = None  # Clear previous errors
            if step.check_done():
                step.status = StepStatus.DONE
            else:
                step.status = StepStatus.PENDING
                
        # 2. Logic propagation (Infer completion from later steps)
        # If a later step is DONE, earlier dependent steps must be DONE too.
        
        # Step 6 (Apply Mute) DONE -> Step 5 (Gen Mute) DONE
        if self.steps[5].status == StepStatus.DONE:
             self.steps[4].status = StepStatus.DONE
             
        # Step 5 (Gen Mute) DONE -> Step 3 (Transcribe) DONE
        # (Step 4 is optional, so we skip checking it here)
        if self.steps[4].status == StepStatus.DONE:
             self.steps[2].status = StepStatus.DONE

        # Step 4 (Merge) DONE -> Step 3 (Transcribe) DONE
        if self.steps[3].status == StepStatus.DONE:
             self.steps[2].status = StepStatus.DONE
             
        # Step 3 (Transcribe) DONE -> Step 2 (Upload) DONE
        if self.steps[2].status == StepStatus.DONE:
             self.steps[1].status = StepStatus.DONE
             
        # Step 2 (Upload) DONE -> Step 1 (Extract) DONE
        if self.steps[1].status == StepStatus.DONE:
             self.steps[0].status = StepStatus.DONE
                
    def apply_force_cascade(self, force_from: int):
        """Apply force flag starting from a step, cascading to later steps."""
        for step in self.steps:
            if step.number >= force_from:
                step.force = True
                step.skip = False  # Cannot skip forced steps
                
    def apply_stop_after(self, stop_after: int):
        """Mark all steps after stop_after as skipped."""
        for step in self.steps:
            if step.number > stop_after:
                step.skip = True
                
    def get_steps_to_run(self) -> List[PipelineStep]:
        """Determine which steps will actually execute."""
        result = []
        for step in self.steps:
            if step.skip:
                continue
            if step.force or step.status == StepStatus.PENDING:
                result.append(step)
        return result
        
    def get_summary(self) -> Dict:
        """Generate a summary for user confirmation."""
        to_run = self.get_steps_to_run()
        to_skip = [s for s in self.steps if s.skip]
        already_done = [s for s in self.steps if s.status == StepStatus.DONE and not s.force and not s.skip]
        
        return {
            "will_run": [(s.number, s.name) for s in to_run],
            "will_skip": [(s.number, s.name) for s in to_skip],
            "already_done": [(s.number, s.name) for s in already_done],
            "warnings": [self.context.audio_track_warning] if self.context.audio_track_warning else [],
        }
        
    def run(self, callback=None):
        """Execute the pipeline."""
        steps_to_run = self.get_steps_to_run()
        
        for idx, step in enumerate(steps_to_run):
            step.status = StepStatus.RUNNING
            if callback:
                callback(step)
                
            try:
                step.execute()
                step.status = StepStatus.DONE
            except Exception as e:
                step.status = StepStatus.ERROR
                step.error_message = str(e)
                print(f"  ERROR in Step {step.number}: {e}")
                if callback:
                    callback(step)
                # Mark remaining steps as skipped due to error
                for remaining in steps_to_run[idx + 1:]:
                    remaining.status = StepStatus.SKIPPED
                    remaining.error_message = f"Skipped due to error in Step {step.number}"
                    if callback:
                        callback(remaining)
                break
                
            if callback:
                callback(step)


def create_pipeline_for_video(video_path: Path, response_folder: Path = None) -> Pipeline:
    """Factory function to create a pipeline for a video."""
    ctx = PipelineContext(
        video_path=video_path,
        response_folder=response_folder or Path("./data/google_api")
    )
    pipeline = Pipeline(ctx)
    pipeline.discover_paths()
    pipeline.detect_status()
    return pipeline
