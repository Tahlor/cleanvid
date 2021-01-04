import os
import delegator
import pickle
import traceback
from pathlib import Path
from easydict import EasyDict as edict
import google_api

FFMPEG = "ffmpeg "

def ffmpeg(func):
    """ Make the appropriate directories, raise error on failure, etc.

    Args:
        func:

    Returns:

    """
    def wrapper(input, output=None, overwrite=True, *args, ffmpeg_path="ffmpeg ", **kwargs):
        ffmpeg_path = FFMPEG if ffmpeg_path is None else ffmpeg_path
        if not output is None:
            Path(output).parent.mkdir(parents=True, exist_ok=True)

        if output is None:
            output = Path(input).parent / (Path(input).stem + "_DYN_AUDIO" + Path(input).suffix) # dynamic audio on all
        output = match_suffix(input, output)

        if not output.exists() or overwrite:
            ffmpegResult, output = func(input, output, *args, **kwargs, ffmpeg_path=ffmpeg_path)
            if (ffmpegResult.return_code != 0) or (not os.path.isfile(output)):
                print(ffmpegResult.err)
                raise ValueError('Could not process %s' % (output))
            return ffmpegResult, output
        else:
            return True, output

    return wrapper

def blank_sections():
    """ Replace video with blank screen

    Returns:

    """
    #command = f"""{ffmpeg_path} -ss {start_time} -to {end_time} -i "{path}" -f segment -segment_time {length} {codec_command} -af dynaudnorm -vf drawbox=color=black:t=fill {output_str}"""
    pass

def skip_sections():
    """ Skip video and audio for section

    Returns:

    """
    # ffmpeg -i input.mp4 -filter_complex '[0:v] trim=end=01:21:47 [v1], [0:a] atrim=end=01:21:47 [a1], [0:v] trim=start=01:22:24 [v2], [0:a] atrim=start=01:22:24 [a2], [v1][a1][v2][a2] concat=n=2:v=1:a=1 [v][a]' -map '[v]' -map '[a]' output.mp4
    pass

@ffmpeg
def trim_video(input, output=None, start="00:00:00", end="99:00:00", ffmpeg_path=None):
    if output is None:
        output = Path(input).parent / (Path(input).stem + "_TRIM" + Path(input).suffix)
    else:
        if Path(output).suffix != Path(input).suffix:
            output = Path(output).with_suffix(Path(input).suffix)

    command = f"""{ffmpeg_path} -y -i "{input}" -ss {start} -to {end} "{output}" """
    print(command)
    ffmpegResult = delegator.run(command, block=True)

    return ffmpegResult, output

def match_suffix(input, out):
    if Path(out).suffix != Path(input).suffix:
        output = Path(out).with_suffix(Path(input).suffix)
    return output

@ffmpeg
def remove_video_track(input, output=None, ffmpeg_path=None):
    if output is None:
        output = Path(input).parent / (Path(input).stem + "_NO_VIDEO" + Path(input).suffix)
    output = match_suffix(input, output)
    command = f"""{ffmpeg_path} -y -i "{input}" -vn "{output}" """
    ffmpegResult = delegator.run(command, block=True)
    return ffmpegResult, output

@ffmpeg
def process_video(input, output=None, ffmpeg_path=None, blank_video="", overwrite=True):
    blank_video = "-vf drawbox=color=black:t=fill" if blank_video else ""
    command = f"""{ffmpeg_path} -y -i "{input}" -af dynaudnorm -ac 1 {blank_video} "{output}" """
    ffmpegResult = delegator.run(command, block=True)
    return ffmpegResult, output

@ffmpeg
def process_audio(input, output, ffmpeg_path="ffmpeg ",
                sample_rate=44100, codec="mp3"):
    if codec[0] != ".":
        codec = "." + codec
    if codec == ".flac":
        codec_command = "-c:a flac "
    elif codec == ".mp3":
        codec_command =  f"-ar {sample_rate} "
    else:
        codec_command = ""

    if output[-len(codec):] != codec:
        output_str = str(Path(output).with_suffix(codec))

    command = f"""{ffmpeg_path} -y -i "{input}" {codec_command} -af dynaudnorm -ac 1 -vn {output_str}"""
    ffmpegResult = delegator.run(command, block=True)
    return ffmpegResult, output


def split_audio(path, name=None, length=3600, start_time="00:00:00", end_time="99:59:59", ffmpeg_path="ffmpeg ",
                sample_rate=44100, codec="mp3"):
    """ Split video into 1 hour segments

    """
    if name is None:
        name = path.stem

    output = f"./temp/{name}/%03d"
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    output_str = f'"{output}.{codec}"'
    if codec == "flac":
        codec_command = "-c:a flac "
    elif codec == "mp3":
        codec_command =  f"-ar {sample_rate} "
    else:
        codec_command = ""

    command = f"""{ffmpeg_path} -i -y "{path}" -f segment -segment_time {length} -ss {start_time} -to {end_time} {codec_command} -af dynaudnorm -ac 1 -vn {output_str}"""
    # -ac 1 : one audio channel
    # -vn   : exclude video

    print(command)
    ffmpegResult = delegator.run(command, block=True)
    return ffmpegResult, output

def split_video(path, name=None, length=3600, start_time="00:00:00", end_time="99:59:59", ffmpeg_path=None):
    """ Split video into 1 hour segments

    """
    ffmpeg_path = FFMPEG if ffmpeg_path is None else ffmpeg_path
    if name is None:
        name = path.stem

    output = f"./temp/{name}/%03d"
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    # if AVI, convert to MP4
    codec = ""
    codec_command = ""
    output_str = f'"{output}.{codec}"'


    #command = f"""{ffmpeg_path} -i "{path}" -f segment -segment_time {length} -ss {start_time} -to {end_time} {codec_command} -af dynaudnorm -ac 1 "{output_str}" """
    command = f"""{ffmpeg_path} -ss {start_time} -to {end_time} -i "{path}" -f segment -segment_time {length} {codec_command} -af dynaudnorm -vf drawbox=color=black:t=fill {output_str}"""
    # -ac 1 : one audio channel
    # -vn   : exclude video
    # -af dynaudnorm : make sound volumes all the same (for background swears)
    # -vf drawbox=color=black:t=fill : replace video with black
    print(command)
    ffmpegResult = delegator.run(command, block=True)
    return ffmpegResult, output


def process_config(path="./config"):
    from configparser import ConfigParser
    config = ConfigParser()
    config.read(path)
    config.getboolean('main', 'require_api_confirmation')  # require confirmation before performing a billed process
    config.getboolean('main', 'testing')
    my_config = {s: dict(config.items(s)) for s in config.sections()}
    for s in config.sections():
        for key,item in my_config[s].items():
            if item.lower() == "true":
                my_config[s][key] = True
            elif item.lower() == "false":
                my_config[s][key] = False

        my_config.update(config.items(s))
    return edict(my_config)

def create_mute_list(time_list):
    """

    Args:
        subs (tuple): a list of tuples (start,end)

    Returns:

    """

    muteTimeList = []
    for timePair in time_list:
        lineStart = timePair[0]
        lineEnd = timePair[1]
        muteTimeList.append("volume=enable='between(t," + format(lineStart-.1, '.3f') + "," + format(lineEnd+.1, '.3f') + ")':volume=0")
    return muteTimeList


def parse_swears(swears="swears.txt"):
    with open(swears) as f:
        lines = [line.rstrip('\n').split("|")[0] for line in f]
    return lines

def create_clean_video(input_path, mute_list, output_path, testing=False, ffmpeg_path="ffmpeg "):
    output_ext = Path(input_path).suffix

    testing = "-to 00:01:00" if testing else ""
    command = f"""{ffmpeg_path} -y -i "{input_path}" -map 0:v:0 -c:v copy  """ + \
              f""" -filter_complex "[a:0]{",".join(mute_list)}[a]" {testing}""" + \
              f""" -metadata:s:a:0 title="Clean",language=eng -metadata:s:a:1 title="Normal" -map "[a]" -c:a:0 aac -map 0:a -c:a:1 copy  """ + \
              f""" "{str(Path(output_path).with_suffix(output_ext))}" """

    """
    -y – A global option to overwrite the output file if it already exists.
    -map 0:v – Designate the video stream(s) from the first input as a source for the output file.
    -c:v copy – Stream copy the video. This just muxes the input to the output. No re-encoding occurs.
    -map 0:a – Designate the audio stream(s) from the first input as a source for the output file.
    -c:a copy – Stream copy the audio. This just muxes the input to the output. No re-encoding occurs.
    -strict -2 -c:a aac – Use the native FFmpeg AAC audio encoder. -strict -2 is required as a way that you acknowledge that the encoder is designated as experimental. It is not a great encoder, but it is not too bad at higher bitrates.

    """

    # "ffmpeg -i video -c:v copy -af volume=0:enable='between(t,60,100)+between(t,330,370)+between(t,465,541.3)' out.mp4"

    print(command)
    ffmpegResult = delegator.run(command,
                                 block=True)
    if (ffmpegResult.return_code != 0) or (not os.path.isfile(output_path)):
        print(ffmpegResult.err)
        raise ValueError('Could not process %s' % (input_path))


if __name__=="__main__":
    config = process_config()
    ga = google_api(**config)
    ga.resume_operation(config.operation_path)
