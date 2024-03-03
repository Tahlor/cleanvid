import json
import subprocess
import os
import delegator
import pickle
import traceback
from pathlib import Path
from easydict import EasyDict as edict
import google_api
import re
import warnings

FFMPEG = "ffmpeg "
VALID_FLOAT_REGEX = re.compile(r"^\d+\.?\d*")

ROOT = Path(__file__).parent.absolute()
while True:
    if ROOT.name != "cleanvid" and ROOT:
        ROOT = ROOT.parent
    else:
        break

def file_exists(path, min_size=1000):
    return Path(path).exists() and os.path.getsize(path) > min_size

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

        if not file_exists(output) or overwrite:
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

    command = f"""{ffmpeg_path} -ss {start} -to {end} -y -i "{input}" "{output}" """
    print(command)
    ffmpegResult = delegator.run(command, block=True)

    return ffmpegResult, output

def match_suffix(input, out):
    if Path(out).suffix != Path(input).suffix:
        out = Path(out).with_suffix(Path(input).suffix)
    return out

@ffmpeg
def remove_video_track(input, output=None, ffmpeg_path=None):
    if output is None:
        output = Path(input).parent / (Path(input).stem + "_NO_VIDEO" + Path(input).suffix)
    output = match_suffix(input, output)
    command = f"""{ffmpeg_path} -y -i "{input}" -vn "{output}" """
    ffmpegResult = delegator.run(command, block=True)
    return ffmpegResult, output

@ffmpeg
def process_video(input, output=None, ffmpeg_path=None, blank_video="", overwrite=True, normalize_audio=False):
    #blank_video = "-vf drawbox=color=black:t=fill" if blank_video else ""
    blank_video = "-vn" if blank_video else ""
    normalize_audio = "-af dynaudnorm" if normalize_audio else ""
    shrink = "-s 2x2"
    codec = " -acodec copy "
    command = f"""{ffmpeg_path} -y -i "{input}" {normalize_audio} -ac 1 {blank_video} {shrink} -threads 4 {codec} "{output}" """
    print(command)
    ffmpegResult = delegator.run(command, block=True)
    return ffmpegResult, output

@ffmpeg
def process_audio(input, output, ffmpeg_path="ffmpeg ",
                sample_rate=44100, codec="mp3", normalize_audio=True):
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
    else:
        output_str = str(output)

    normalize_audio = "-af dynaudnorm" if normalize_audio else ""

    command = f"""{ffmpeg_path} -y -i "{input}" {codec_command} {normalize_audio} -ac 1 -vn {output_str}"""
    ffmpegResult = delegator.run(command, block=True)
    return ffmpegResult, output


def split_audio(path, name=None, length=3600, start_time="00:00:00", end_time="99:59:59", ffmpeg_path="ffmpeg ",
                sample_rate=44100, codec="mp3", normalize_audio=True):
    """ Split audio into 1 hour segments

    Args:
        path: path to video
        name: name of output file
        length: length of each segment
        start_time: start time of video
        end_time: end time of video
        ffmpeg_path: path to ffmpeg
        sample_rate: sample rate of output audio
        codec: codec of output audio
        normalize_audio (bool): normalize audio (default is True for audio files, false for video files)

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
    normalize_audio = "-af dynaudnorm" if normalize_audio else ""
    command = f"""{ffmpeg_path} -ss {start_time} -to {end_time} -i -y "{path}" -f segment -segment_time {length} {codec_command} {normalize_audio} -ac 1 -vn {output_str}"""
    # -ac 1 : one audio channel
    # -vn   : exclude video

    print(command)
    ffmpegResult = delegator.run(command, block=True)
    return ffmpegResult, output

def split_video(path, name=None, length=3600, start_time="00:00:00", end_time="99:59:59", ffmpeg_path=None, normalize_audio=False):
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


    #command = f"""{ffmpeg_path} -i "{path}" -f segment -segment_time {length} -ss {start_time} -to {end_time} {codec_command} {normalize_audio} -ac 1 "{output_str}" """
    normalize_audio = "-af dynaudnorm" if normalize_audio else ""
    shrink = "-s 2x2"
    command = f"""{ffmpeg_path} -ss {start_time} -to {end_time} -i "{path}" {shrink} -f segment -segment_time {length} {codec_command} {normalize_audio} -vf drawbox=color=black:t=fill {output_str}"""
    # -ac 1 : one audio channel
    # -vn   : exclude video
    # -af dynaudnorm : make sound volumes all the same (for background swears)
    # -vf drawbox=color=black:t=fill : replace video with black
    print(command)
    ffmpegResult = delegator.run(command, block=True)
    return ffmpegResult, output


def process_config(path=ROOT / "configs/default_config",
                   video_path="",
                   response_path="",
                   mute_list="",
                   pickle_path=""):
    from configparser import ConfigParser
    config = ConfigParser()
    assert Path(path).exists()
    config.read(path)
    # config["main"]["require_api_confirmation"] = config.getboolean('main', 'require_api_confirmation')  # require confirmation before performing a billed process
    # config["main"]["testing"] = config.getboolean('main', 'testing')
    my_config = {s: dict(config.items(s)) for s in config.sections()}

    # DEFAULTS
    my_config["google_api_request_made"] = False
    my_config["google_api_request_allowed"] = True

    if video_path:
        my_config["main"]["video_path"] = video_path
    if response_path:
        my_config["paths"]["load_response_path"] = response_path
    if mute_list:
        my_config["paths"]["mute_list_path"] = mute_list
    if pickle_path:
        my_config["paths"]["pickle_path"] = pickle_path

    # Make paths relative to root
    for k,v in my_config["paths"].items():
        if not Path(v).exists():
            my_config["paths"][k] = ROOT / v

    if not "uri" in my_config["main"]:
        if "video_path" not in my_config["main"]:
            raise Exception("Must specify video path in config or process_config argument")
        p = Path(my_config["main"]["video_path"])
        name = re.sub('[^-a-zA-Z_0-9]+', "", re.sub('[. _]+', "_", p.stem))
        my_config["main"]["uri"] = rf"gs://remove_profanity_from_movie_project/{name}{p.suffix}"

    if "clean_video_path" not in my_config:
        video_path = Path(my_config["main"]["video_path"])
        my_config["paths"]["clean_video_path"] = video_path.parent / (video_path.stem + "_clean" + video_path.suffix)
        my_config["paths"]["video_output_root"] = Path(my_config["paths"]["clean_video_path"]).parent

    for s in config.sections():
        for key,item in my_config[s].items():
            if str(item).lower().strip() == "true":
                my_config[s][key] = True
            elif str(item).lower().strip() == "false":
                my_config[s][key] = False

        # Put all options on the top level, e.g. get rid of "Main", "paths", etc. sections
        my_config.update(my_config[s].items())

    return edict(my_config), config

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


def parse_swears(swears= ROOT / "swears.txt"):
    with open(swears) as f:
        lines = [line.rstrip('\n').split("|")[0] for line in f]
    return lines

def format_mute_list(mute_list, mute_list_file):
    formatted_mute_list = f"""[a:0]{",".join(mute_list)}[a]"""
    if mute_list_file:
        # if Path(mute_list_file).exists():
        #     input("Mute list file exists, overwrite?")
        with mute_list_file.open("w") as f:
            f.write(formatted_mute_list)
    return formatted_mute_list

def check_for_mute_list(input_video_path):
    input_video_path = Path(input_video_path)
    mute_list_path = input_video_path.parent / (input_video_path.stem + "_clean_MUTE.txt")
    if mute_list_path.exists():
        print("Mute list exists, using it")
        return mute_list_path
    else:
        return None

def check_for_response_file(input_video_path, response_folder):
    input_video_path = Path(input_video_path)
    files = list(Path(response_folder).rglob(input_video_path.stem + "*.response"))
    if files:
        use_response = input("Response file exists! Use it? (y/n)")
        if use_response.lower() == "y":
            return files[-1]
    return None

def create_clean_video_command(input_path, output_path, mute_list=None, testing=False, ffmpeg_path="ffmpeg ",
                               mute_list_file=None):
    output_ext = Path(input_path).suffix
    if mute_list_file is None:
        mute_list_file = output_path.parent / (output_path.stem + "_MUTE.txt")
        formatted_mute_list = format_mute_list(mute_list,mute_list_file)
    testing = "-to 00:01:00" if testing else ""

    ffprobe_json = get_ffprobe_json(input_path)
    audio_format = get_audio_encoding_from_ffprobe_json(ffprobe_json)
    try:
        audio_bitrate = f"{int(get_audio_bitrate_from_ffprobe_json(ffprobe_json)) // 1000}k"
    except:
        audio_bitrate = "256k"

    command = f"""{ffmpeg_path} -y -i "{input_path}" -map 0:v:0 -c:v copy  """ + \
              f""" -filter_complex_script "{mute_list_file}"  {testing}""" + \
              f""" -metadata:s:a:0 title="Clean" -metadata:s:a:0 language=eng -metadata:s:a:1 title="Original" -map "[a]" -c:a:0 {audio_format} -b:a:0 {audio_bitrate} -map 0:a -c:a:1 copy  """ + \
              f"""-disposition:a:0 default""" + \
              f""" "{str(Path(output_path).with_suffix(output_ext))}" """
    # f""" -threads 4 """ + \

    r"""
    -y – A global option to overwrite the output file if it already exists.
    -map 0:v – Designate the video stream(s) from the first input as a source for the output file.
    -c:v copy – Stream copy the video. This just muxes the input to the output. No re-encoding occurs.
    -map 0:a – Designate the audio stream(s) from the first input as a source for the output file.
    -c:a copy – Stream copy the audio. This just muxes the input to the output. No re-encoding occurs.
    -strict -2 -c:a aac – Use the native FFmpeg AAC audio encoder. -strict -2 is required as a way that you acknowledge that the encoder is designated as experimental. It is not a great encoder, but it is not too bad at higher bitrates.
    -disposition:a:0 default first stream is default audio track
    -c copy - copy only default streams
    -map 0 - copy all streams

    # CHANGE TO DEFAULT CLEAN AUDIO TRACK (sample)
    ffmpeg -i "J:\Media\Videos\Movies\Unorganized\Apollo.13.1995.REMASTERED.1080p.BluRay.x265-RARBG\Apollo.13.1995_clean.mp4"  -ss 00:21:00 -to 00:21:20 -c copy -map 0 -metadata:s:a:0 title="Clean" -metadata:s:a:0 language=eng -metadata:s:a:1 title="Original" -disposition:a:0 default  "J:\Media\Videos\Movies\Unorganized\Apollo.13.1995.REMASTERED.1080p.BluRay.x265-RARBG\Apollo.13.1995_clean2.mp4"

    """

    # "ffmpeg -i video -c:v copy -af volume=0:enable='between(t,60,100)+between(t,330,370)+between(t,465,541.3)' out.mp4"

    print(command)
    return command, mute_list_file

def create_clean_video(input_path,
                       output_path,
                       mute_list=None,
                       testing=False,
                       ffmpeg_path="ffmpeg ",
                       del_mute_list_after=False,
                       mute_list_file=None):

    if mute_list is None and mute_list_file is None:
        mute_list_file = check_for_mute_list(input_path)
        if mute_list_file is None:
            raise ValueError("No mute list provided")
        else:
            warnings.warn("No mute list provided, using discovered mute list {}".format(mute_list_file))

    command, mute_list_file = create_clean_video_command(input_path, output_path, mute_list, testing, ffmpeg_path,
                                                         mute_list_file=mute_list_file)
    ffmpegResult = delegator.run(command,
                                 block=True)
    if (ffmpegResult.return_code != 0) or (not os.path.isfile(output_path)):
        print(ffmpegResult.err)
        raise ValueError('Could not process %s' % (input_path))

    if del_mute_list_after:
        os.remove(mute_list_file)


def get_length(filename, ffprobe_path=r"ffprobe"):
    command = [str(ffprobe_path), "-v", "error", "-show_entries",
               "format=duration", "-of",
               "default=noprint_wrappers=1:nokey=1", str(filename)]
    print(" ".join(command))
    result = subprocess.run(command,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    valid_float = VALID_FLOAT_REGEX.match(result.stdout.decode()).group(0)
    return float(valid_float)

def get_ffprobe_json(filename, ffprobe_path=r"ffprobe"):
    command = [str(ffprobe_path), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-show_error",
               str(filename)]
    print(" ".join(command))
    result = subprocess.run(command,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    return json.loads(result.stdout)

def get_audio_encoding_from_ffprobe_json(ffprobe_json):
    streams = ffprobe_json["streams"]
    for stream in streams:
        if stream["codec_type"] == "audio":
            return stream["codec_name"]

def get_audio_bitrate_from_ffprobe_json(ffprobe_json):
    streams = ffprobe_json["streams"]
    for stream in streams:
        if stream["codec_type"] == "audio":
            return stream["bit_rate"]

def config_parser_test():
    config, _config_parser = process_config(video_path="example/video.mp4")
    print(config.uri)

def audio_encoding_test():
    ffprobe_json = get_ffprobe_json("J:\Media\Videos\Misc Videos\msc\The Dropout\The.Dropout.S01E01.mkv")
    print(get_audio_encoding_from_ffprobe_json(ffprobe_json))
    print(get_audio_bitrate_from_ffprobe_json(ffprobe_json))

if __name__=="__main__":
    audio_encoding_test()
    #ga = google_api(**config)
    #ga.resume_operation(config.operation_path)
