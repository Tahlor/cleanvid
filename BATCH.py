import warnings
import argparse
import pickle
import clean_audio
import utils
from pathlib import Path
from datetime import datetime

today = datetime.today()
MONTH = datetime(today.year, today.month, 1).strftime("%B")
video_extensions = ["*.mp4","*.avi", "*.mkv", "*.m4v"]
UTILIZATION = {}
MAX_UTILIZATION = 60*1000

def process_batch_list(batch_list, config, video_path):
    global UTILIZATION
    if video_path:
        if batch_list:
            print("Video path specified, ignoring batch list")
        batch_list=[video_path]
    else:
        with Path(batch_list).open("r") as f:
            batch_list = f.read().strip().replace("'","").replace('"',"").split("\n")

    UTILIZATION = load_utilization()
    #print(UTILIZATION)
    #UTILIZATION[MONTH] = 480*60

    # load list
    for item in batch_list:
        if UTILIZATION[MONTH] > MAX_UTILIZATION:
            warnings.warn("MAX utilization reached")
            break
        item = search_folder_for_video(item)
        if item:
            print("Working on ", Path(item).name)
            config, _config_parser = utils.process_config(opts.config, video_path=item)
            total_length = utils.get_length(item, Path(config.ffmpeg_path).parent/"ffprobe")
            total_length = round(total_length+7.49,15)
            if total_length > 1200: # should be longer than 20 minutes
                success = process_item(config)
                if success:
                    UTILIZATION[MONTH] += total_length
            else:
                print(item, "less than 1000 seconds, skipping", total_length)
        else:
            print(item, "not found")

    print("New Utilization", MONTH, UTILIZATION[MONTH])
    save_utilization(UTILIZATION)

def search_folder_for_video(folder):
    if Path(folder).suffix in video_extensions:
        return folder
    else:
        for ext in video_extensions:
            for i in Path(str(folder).lower()).rglob(ext):
                if "_clean" in i.name.lower() or (i.parent / (i.stem + "_clean" + i.suffix)).exists() :
                    print("Clean version detected", i.name)
                    return False
                if "sample" not in i.name:
                    return i
        return False

def process_item(config):
    try:
        cp = clean_audio.CleanProfanity(**config)
        return cp.main(config.video_path,
                overwrite_cloud=config.overwrite.overwrite_cloud,
                overwrite_local=config.overwrite.overwrite_ffmpeg_files,
                testing=config.testing,
                blank_video=config.blank_video,
                uri=config.uri,
                already_processed_okay=False)
    except Exception as e:
        print(e)
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
    return UTILIZATION

def save_utilization(utilization):
    with Path("./personal/utilization").open("wb") as f:
        pickle.dump(utilization, f)

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('config', nargs='?', default='')
    parser.add_argument('--batch_file', type=str, default='./personal/BATCH.txt', help='Path to the batch_file')
    parser.add_argument('--video', type=str, default='', help='Path to the video')

    opts = parser.parse_args()
    if not opts.config:
        opts.config = "configs/default_config"

    process_batch_list(batch_list=opts.batch_file, config=opts.config, video_path=opts.video)