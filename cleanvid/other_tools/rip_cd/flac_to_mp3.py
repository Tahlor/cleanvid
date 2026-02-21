import os
import subprocess
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- Configuration ---
# Use Path objects for configuration
input_folder = Path(r"C:\Users\Taylor\Music\Marcie Gallacher & Kerri Robinson")
output_folder = Path(r"C:\Users\Taylor\Music\Converted_MP3s")


# ---------------------

class FlacConverter(FileSystemEventHandler):
    def on_created(self, event):
        # Convert the string path from the event to a Path object
        src_path = Path(event.src_path)
        if not event.is_directory and src_path.suffix.lower() == ".flac":
            self.wait_for_file_to_stabilize(src_path)

    def wait_for_file_to_stabilize(self, file_path: Path):
        """
        Waits for the file to stop changing in size before processing.
        """
        print(f"New FLAC file detected: {file_path}")
        last_size = -1
        # Wait for a maximum of 30 seconds for the file to stabilize
        for _ in range(15):
            try:
                # Use pathlib to get file size and check existence
                if not file_path.exists():
                    print(f"File {file_path.name} disappeared. Skipping.")
                    return
                current_size = file_path.stat().st_size
                if current_size == last_size and current_size > 0:
                    print("File size has stabilized. Starting conversion.")
                    self.process(file_path)
                    return
                last_size = current_size
                time.sleep(2)  # Wait 2 seconds between checks
            except Exception as e:
                print(f"An error occurred while checking file stability: {e}")
                return
        print(f"File {file_path.name} did not stabilize in time. Skipping.")

    def process(self, flac_path: Path):
        """
        Converts a FLAC file to a mono, 64kbps MP3 using pathlib.
        """
        try:
            # Use pathlib to construct paths elegantly
            relative_path = flac_path.parent.relative_to(input_folder)
            output_dir = output_folder / relative_path
            # Use pathlib to create directories
            output_dir.mkdir(parents=True, exist_ok=True)

            # Use .stem for the filename without extension
            output_mp3_path = output_dir / f"{flac_path.stem}.mp3"

            if output_mp3_path.exists():
                print(f"Output for {flac_path.name} already exists. Skipping.")
                return

            print(f"Converting: {flac_path}")
            print(f"      -> To: {output_mp3_path}")

            command = [
                'ffmpeg',
                '-i', str(flac_path),  # Convert Path to string for subprocess
                '-ac', '1',
                '-b:a', '64k',
                '-map_metadata', '0',
                '-id3v2_version', '3',
                str(output_mp3_path)  # Convert Path to string for subprocess
            ]
            subprocess.run(command, check=True, capture_output=True, text=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            print("Conversion successful!")

        except subprocess.CalledProcessError as e:
            print(f"Error during conversion: {e.stderr}")
        except Exception as e:
            print(f"An error occurred: {e}")


def process_existing_files(input_dir: Path, output_dir: Path, converter: FlacConverter):
    """
    Scans for and converts existing FLAC files using pathlib.
    """
    print("--- Starting scan for existing files ---")
    # Use rglob to efficiently find all .flac files recursively
    for flac_path in input_dir.rglob("*.flac"):
        relative_path = flac_path.parent.relative_to(input_dir)
        output_mp3_path = output_dir / relative_path / f"{flac_path.stem}.mp3"

        if not output_mp3_path.exists():
            converter.process(flac_path)
    print("--- Initial scan complete. Now monitoring for new files. ---")


if __name__ == "__main__":
    # Use is_dir() method from pathlib
    if not input_folder.is_dir():
        print(f"Error: Input folder not found at '{input_folder}'")
    else:
        event_handler = FlacConverter()

        process_existing_files(input_folder, output_folder, event_handler)

        observer = Observer()
        # The observer needs the path as a string
        observer.schedule(event_handler, str(input_folder), recursive=True)
        observer.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()