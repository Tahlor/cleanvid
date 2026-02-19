"""
CleanVid CLI - Pipeline Runner

This script provides command-line access to the 6-step pipeline.
"""

import sys
import argparse
from pathlib import Path

# Add root directory to sys.path
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

from scripts.pipeline import create_pipeline_for_video, StepStatus


def main():
    parser = argparse.ArgumentParser(
        description="CleanVid Pipeline: Clean profanity from videos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze a video (show status, no execution)
  python run_pipeline.py --video_file "movie.mp4" --analyze
  
  # Run full pipeline
  python run_pipeline.py --video_file "movie.mp4"
  
  # Force redo from Step 3 (transcription) onwards
  python run_pipeline.py --video_file "movie.mp4" --force_step 3
  
  # Enable subtitle merge (Step 4, normally skipped)
  python run_pipeline.py --video_file "movie.mp4" --do_merge
  
  # Run only up to Step 5 (generate mute list, don't create video)
  python run_pipeline.py --video_file "movie.mp4" --stop_after 5
"""
    )
    
    # Input
    parser.add_argument("--video_file", required=True, help="Path to video file")
    parser.add_argument("--responses", default="./data/google_api", help="Response folder")
    
    # Overrides
    parser.add_argument("--subtitle_file", help="Override subtitle file path")
    parser.add_argument("--response_file", help="Override response file path")
    
    # Pipeline Control
    parser.add_argument("--force_step", type=int, choices=[1,2,3,4,5,6], 
                        help="Force redo from this step (cascades forward)")
    parser.add_argument("--stop_after", type=int, choices=[1,2,3,4,5,6],
                        help="Stop after this step")
    parser.add_argument("--do_merge", action="store_true",
                        help="Enable Step 4 (Merge Subtitles) - normally skipped")
    parser.add_argument("--skip_merge", action="store_true", default=True,
                        help="Skip Step 4 (default)")
    
    # Mode
    parser.add_argument("--analyze", action="store_true",
                        help="Analyze only, don't execute")
    
    args = parser.parse_args()
    
    # Create pipeline
    video_path = Path(args.video_file)
    if not video_path.exists():
        print(f"Error: Video file not found: {video_path}")
        sys.exit(1)
        
    print(f"Creating pipeline for: {video_path.name}")
    pipeline = create_pipeline_for_video(video_path, Path(args.responses))
    
    # Apply overrides
    if args.subtitle_file:
        pipeline.context.subtitle_path = Path(args.subtitle_file)
    if args.response_file:
        pipeline.context.response_path = Path(args.response_file)
        
    # Apply merge control
    if args.do_merge:
        pipeline.steps[3].skip = False  # Step 4 is index 3
    else:
        pipeline.steps[3].skip = True
        
    # Apply force cascade
    if args.force_step:
        pipeline.apply_force_cascade(args.force_step)
        
    # Apply stop
    if args.stop_after:
        pipeline.apply_stop_after(args.stop_after)
    
    # Show summary
    summary = pipeline.get_summary()
    
    print("\n=== Pipeline Analysis ===")
    print(f"Video: {video_path.name}")
    print(f"Audio tracks: {pipeline.context.audio_track_count}")
    if pipeline.context.audio_track_warning:
        print(f"⚠ WARNING: {pipeline.context.audio_track_warning}")
    print()
    
    print("Steps:")
    for step in pipeline.steps:
        status_char = "✓" if step.status == StepStatus.DONE else "○"
        force_mark = " [FORCE]" if step.force else ""
        skip_mark = " [SKIP]" if step.skip else ""
        print(f"  {step.number}. {status_char} {step.name}{force_mark}{skip_mark}")
    print()
    
    if summary['will_run']:
        print("Will Execute:")
        for num, name in summary['will_run']:
            print(f"  → Step {num}: {name}")
    else:
        print("Nothing to execute (all done or skipped).")
        
    if args.analyze:
        print("\n[Analyze mode - no execution]")
        return
        
    # Confirm and run
    print()
    response = input("Proceed? [y/N]: ")
    if response.lower() != 'y':
        print("Aborted.")
        return
        
    print("\n=== Running Pipeline ===")
    
    def callback(step):
        if step.status == StepStatus.RUNNING:
            print(f"  ⟳ Step {step.number}: {step.name}...")
        elif step.status == StepStatus.DONE:
            print(f"  ✓ Step {step.number}: Done")
        elif step.status == StepStatus.ERROR:
            print(f"  ✗ Step {step.number}: ERROR - {step.error_message}")
            
    pipeline.run(callback=callback)
    
    print("\n=== Complete ===")


if __name__ == "__main__":
    main()
