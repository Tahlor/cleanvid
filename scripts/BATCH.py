import traceback
import warnings
import argparse
import pickle
from pathlib import Path
import os, sys

# Add root directory to sys.path to allow imports from parent
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))
# Also add 'other_tools' to path if needed, but it seems to be imported as a package from root?
# "from other_tools import cleanup_bucket" - this works if root is in sys.path.

import MAIN
import utils
from datetime import datetime
import logging
import my_logging

#logger = logging.getLogger("root." + __name__)
logger = my_logging.setup_logging("./logs", log_name="batch_", datefmt="%m-%d-%Y %H:%M:%S")
from other_tools import cleanup_bucket


video_extensions = ["*.mp4","*.avi", "*.mkv", "*.m4v"]
UTILIZATION = {}
MAX_UTILIZATION = 60*1000
UTILIZATION_EXCEEDED = False
def get_month():
    today = datetime.today()
    return datetime(today.year, today.month, 1).strftime("%Y %B")

def check_month_utilization():
    global MONTH, UTILIZATION_EXCEEDED
    MONTH = get_month()
    if UTILIZATION[MONTH] > MAX_UTILIZATION:
        warnings.warn("MAX utilization reached")
        UTILIZATION_EXCEEDED = True

MONTH = get_month()

def process_batch_list(batch_list, config, video_path, no_video=False):
    cleanup_bucket.cleanup_bucket()
    global UTILIZATION, MONTH
    if video_path:
        if batch_list:
            print("Video path specified, ignoring batch list")
        batch_list=[video_path]
    else:
        with Path(batch_list).open("r") as f:
            batch_list = f.read().strip().replace("'","").replace('"',"").split("\n")
    print(f"Batch {batch_list}")
    UTILIZATION = load_utilization()
    
    # ... (existing code for utilization check) ...
    # Wait, I need to keep the context.
    # I'll just replace the relevant parts.
    
    print(f"Utilization for {MONTH}: {UTILIZATION[MONTH]}")
    #UTILIZATION[MONTH] = 480*60

    # load list
    for item in batch_list:
		# Skip commented ones
        line = item.strip()
        if not line:
            continue
        elif line[0] =="#":
            print(f"skipping {item}")
            continue

        check_month_utilization()

        print(f"Checking if {item} exists...")
        full_items = list(search_folder_for_video(item))
        for full_item in full_items:
            if full_item:
                print("Working on ", Path(full_item).name)
                mute_list = search_for_mute_list(full_item)
                config, _config_parser = utils.process_config(opts.config, video_path=full_item, mute_list=mute_list)
                total_length = utils.get_length(full_item, Path(config.ffmpeg_path).parent/"ffprobe")
                total_length = round(total_length+7.49,15)
                check_month_utilization()
                config["google_api_request_allowed"] = not UTILIZATION_EXCEEDED
                if total_length > 1200: # should be longer than 20 minutes
                    success = process_item(config, _config_parser, no_video=no_video)
                    if success:
                        print("SUCCESS")
                    if config.google_api_request_made:
                        print(f"Adding to utilization {total_length}")
                        UTILIZATION[MONTH] += total_length
                        UTILIZATION[f"{MONTH} dict"][Path(full_item).name] = total_length
                        save_utilization(UTILIZATION)
                        print(f"Total Utilization {MONTH}: {UTILIZATION[MONTH]}")
                    else:
                        print("NOT SUCCESS")
                else:
                    print(full_item, "less than 1000 seconds, skipping", total_length)
            else:
                print(item, "not found")

    print("New Utilization", MONTH, UTILIZATION[MONTH])
    save_utilization(UTILIZATION)

def search_for_mute_list(full_item):
    full_item = Path(full_item)
    mute_list = full_item.parent / (full_item.stem + "_clean_MUTE.txt")
    if mute_list.exists():
        return mute_list
    else:
        return ""

def search_folder_for_video(folder):
    if Path(folder).suffix in [x.replace("*","") for x in video_extensions]:
        print(f"{folder} is video path")
        if clean_exists(folder):
            return False
        yield folder
    else:
        for ext in video_extensions:
            for i in Path(str(folder).lower()).rglob(ext):
                if clean_exists(i):
                    #)print("Clean version detected for:", i.name)
                    yield False
                elif "sample" not in i.name:
                    yield i


def clean_exists(i):
    i = Path(i)
    if "_clean" in i.name.lower() or (i.parent / (i.stem + "_clean" + i.suffix)).exists():
        print("Clean version detected for:", i.name)
        return True
    return False

def process_item(config, _config_parser, no_video=False):
    try:
        MAIN.manager(config, _config_parser, output_config=None, no_video=no_video)
        return True
    except Exception as e:
        traceback.print_exc()
        return False

def load_utilization():
    global UTILIZATION
    try:
        with Path("./personal/utilization").open("rb") as f:
            UTILIZATION = pickle.load(f)
    except Exception as e:
        print(e)
        print("Allotment not found, creating blank dictionary")
        UTILIZATION = {}
    if MONTH not in UTILIZATION:
        UTILIZATION[MONTH] = 0
    if MONTH + " dict" not in UTILIZATION:
        UTILIZATION[MONTH + " dict"] = {}
    return UTILIZATION

def save_utilization(utilization):
    with Path("./personal/utilization").open("wb") as f:
        pickle.dump(utilization, f)

if __name__=='__main__':
    # Load User Config
    no_video_default = False
    try:
        import personal.user_config as user_config
        no_video_default = getattr(user_config, 'NO_VIDEO', False)
        if no_video_default:
            print(f"Loaded user config: NO_VIDEO={no_video_default}")
    except ImportError:
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument('config', nargs='?', default='')
    parser.add_argument('--batch_file', type=str, default='./personal/BATCH.txt', help='Path to the batch_file')
    parser.add_argument('--video', type=str, default='', help='Path to the video')
    
    parser.set_defaults(no_video=no_video_default)
    parser.add_argument('--no-video', action='store_true', help='Skip video creation')

    opts = parser.parse_args()

    # For resuming from an operation / response, just updue the response file in configs/RESUME
    # opts.config = "configs/RESUME"

    if "RESUME" in opts.config:
        warnings.warn("Using config to RESUME previous operation")
    if not opts.config:
        opts.config = "configs/default_config"

    process_batch_list(batch_list=opts.batch_file, config=opts.config, video_path=opts.video, no_video=opts.no_video)
