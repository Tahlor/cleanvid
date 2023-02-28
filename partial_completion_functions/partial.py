from utils import create_clean_video_command
from pathlib import Path
import MAIN

def create_mute_list_from_pickle(video, pickle=None, mute_list=None):
    #MAIN.process_saved_response(video_path=video, pickle_path=pickle)
    if mute_list is None and pickle is None:
        raise Exception("Must specify mutelist or pickle")
    MAIN.main(f"--video='{video}' --mute_list='{mute_list}' --pickle='{pickle}'")

def create_file_from_mute_list(input, output, mute_list_file):
    command, mute_list_file = create_clean_video_command(input, output, mute_list_file=mute_list_file)
    print(command)


# Create mutelist from response:
# process_response_to_mute_list(video_path, response_path, name=None, mute_list_output_path=None)

# Create video from response:
# process_saved_response(video_path, response_path, name=None, mute_list_output_path=None)

if __name__ == '__main__':
    if False:
        dir = Path("J:\Media\Videos\Misc Videos\msc\The Dropout Season 1 Mp4 1080p")
        create_file_from_mute_list(input=dir / "The Dropout S01E07.mp4",
                                   output=dir / "The Dropout S01E07_clean.mp4",
                                   mute_list_file=dir / "The Dropout S01E07_clean_MUTE.txt")
    else:
        pickle = r"D:\Github\cleanvid\data\mute_lists\Father.Stu.2022.1080p.BluRay.x265-RARBG.pickle"
        vid=r"J:\Media\Videos\Movies\Unorganized\Father.Stu.2022.1080p.BluRay.x265-RARBG\Father.Stu.2022.1080p.BluRay.x265-RARBG.mp4"

        create_mute_list_from_pickle(vid, pickle)