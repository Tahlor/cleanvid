import pytest
import utils
import decorator
from pathlib import Path
import os

PATH = os.path.dirname(__file__)
os.chdir(PATH)

def prep(func):
    def wrapper(func, *args, **kwargs):
        for i in Path(f"{PATH}/test_output").glob("*"):
            if i.is_file():
                os.remove(i)
        return func(*args, **kwargs)
    return decorator.decorator(wrapper, func)

@prep
def test_trim_file():
    input_file = f"{PATH}/test_input/copypasta.mp4"
    output_file = f"{PATH}/test_output/copypasta_TRIM.mp4"
    result, output = utils.trim_video(input_file, output_file, start="00:00:15", end="00:00:29")

@prep
def test_remove_video():
    input_file = f"{PATH}/test_input/copypasta.mp4"
    output_file = f"{PATH}/test_output/copypasta_NO_VIDEO.mp4"
    result, output = utils.remove_video_track(input_file, output_file)

@prep
def test_process_video():
    input_file = f"{PATH}/test_input/copypasta.mp4"
    output_file = f"{PATH}/test_output/copypasta_processed_VIDEO.mp4"
    result, output = utils.process_video(input_file, output_file)

@prep
def test_process_audio():
    input_file = f"{PATH}/test_input/copypasta.mp4"
    output_file = f"{PATH}/test_output/copypasta_processed_AUDIO.mp4"
    result, output = utils.process_audio(input_file, output_file)


if __name__=='__main__':
    test_trim_file()
    test_remove_video()
    test_process_audio()
    test_process_video()