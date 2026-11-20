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
import shutil
import uuid

FFMPEG = "ffmpeg "
VALID_FLOAT_REGEX = re.compile(r"^\d+\.?\d*")
AUDIO_CHANNEL_ARG = "" #-ac 1
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
    command = f"""{ffmpeg_path} -y -i "{input}" {normalize_audio} {AUDIO_CHANNEL_ARG} {blank_video} {shrink} -threads 4 {codec} "{output}" """
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

    command = f"""{ffmpeg_path} -y -i "{input}" {codec_command} {normalize_audio} {AUDIO_CHANNEL_ARG} -vn {output_str}"""
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
    command = f"""{ffmpeg_path} -ss {start_time} -to {end_time} -y -i "{path}" -f segment -segment_time {length} {codec_command} {normalize_audio} {AUDIO_CHANNEL_ARG} -vn {output_str}"""
    # -ac 1 : one audio channel
    # -vn   : exclude video

    print(command)
    ffmpegResult = delegator.run(command, block=True)
    
    if ffmpegResult.return_code != 0:
        print(f"Direct access failed: {ffmpegResult.err}")
        # Fallback: Copy to temp and retry
        try:
            print("Attempting fallback: Copying video to local temp...")
            temp_dir = Path("./temp")
            temp_dir.mkdir(exist_ok=True)
            temp_file = temp_dir / f"fallback_{uuid.uuid4()}{Path(path).suffix}"
            
            shutil.copy2(path, temp_file)
            print(f"Copied to {temp_file}, retrying extraction...")
            
            # Recurse with temp file, but KEEP ORIGINAL NAME for output folder stability
            return split_audio(
                temp_file, 
                name=name, 
                length=length, 
                start_time=start_time, 
                end_time=end_time,
                ffmpeg_path=ffmpeg_path,
                sample_rate=sample_rate,
                codec=codec,
                normalize_audio=normalize_audio
            )
            
        except Exception as e:
            print(f"Fallback failed: {e}")
            # Clean up if possible
            if 'temp_file' in locals() and temp_file.exists():
                try:
                    os.remove(temp_file)
                except:
                    pass
            raise ValueError(f"Could not extract audio (primary and fallback failed): {ffmpegResult.err}")
        finally:
             if 'temp_file' in locals() and temp_file.exists():
                try:
                    os.remove(temp_file)
                except:
                    pass

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
    if ffmpegResult.return_code != 0:
        print(ffmpegResult.err)
        raise ValueError(f"Could not split video: {ffmpegResult.err}")
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

def parse_subtitle_exceptions(path=ROOT / "subtitle_exceptions.txt"):
    """Parse words that are bleeped from transcription but allowed if confirmed by subtitles.
    
    Returns:
        set: Words that should be conditionally allowed if present in subtitles.
    """
    if not Path(path).exists():
        return set()
    with open(path) as f:
        lines = [line.strip().lower() for line in f 
                 if line.strip() and not line.strip().startswith('#')]
    return set(lines)

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

def _clean_video_args(input_path, output_path, filter_text, ffmpeg_path, testing=False):
    """Build an argv list (no shell quoting) and retain every non-clean stream."""
    source = get_ffprobe_json(input_path)
    if source.get("error") or not source.get("streams"):
        raise ValueError(f"Invalid source: {input_path}")
    audio = [s for s in source["streams"] if s["codec_type"] == "audio"]
    if not audio:
        raise ValueError("Input has no audio")
    def title(s):
        return s.get("tags", {}).get("title", "").casefold()
    clean = [i for i, s in enumerate(audio) if "clean" in title(s) and "original" not in title(s)]
    original = [i for i, s in enumerate(audio) if "original" in title(s)]
    if len(original) == 1:
        index = original[0]
    elif len(audio) == 1 and not clean:
        index = 0
    elif len(audio) - len(clean) == 1:
        index = next(i for i in range(len(audio)) if i not in clean)
    else:
        raise ValueError("Ambiguous original audio track; label the original before processing")
    if index in clean:
        raise ValueError("Original audio cannot also be a clean track")
    # Historical mute scripts use [a:0] or [0:a:0] and [a]. Keep all
    # saved intervals unchanged; only rebind their audio input and output.
    match = re.fullmatch(r"\[(?:0:)?a:\d+\](.*?)\[a\]", filter_text.strip(), flags=re.S)
    if not match:
        raise ValueError("Unrecognized saved mute script")
    body = match.group(1) or "anull"
    normalized = f"[0:a:{index}]{body}[cleanvid_audio]"
    # Source codecs such as DTS-HD are not suitable encoder choices. AC-3
    # retains up to 5.1 channels; AAC is the portable fallback for other
    # containers and channel counts.
    suffix = Path(output_path).suffix.lower()
    channels = int(audio[index].get("channels", 2))
    codec = "ac3" if suffix in (".mkv", ".mp4", ".m4v") and 3 <= channels <= 6 else "aac"
    bitrate = "448k" if codec == "ac3" else f"{min(768, max(128, 64*channels))}k"
    if suffix not in (".mkv", ".mp4", ".m4v", ".mov", ".avi"):
        raise ValueError(f"Unsupported output container {suffix}")
    args = [str(ffmpeg_path).strip().strip('"'), "-nostdin", "-hide_banner", "-v", "error",
            "-n", "-i", str(input_path), "-filter_complex", normalized, "-map", "0"]
    for i in clean:
        args += ["-map", f"-0:a:{i}"]
    kept = [i for i in range(len(audio)) if i not in clean]
    new_index = len(kept)
    original_output = kept.index(index)
    args += ["-map", "[cleanvid_audio]", "-map_metadata", "0", "-map_chapters", "0",
             "-c", "copy", f"-c:a:{new_index}", codec, f"-b:a:{new_index}", bitrate,
             f"-metadata:s:a:{original_output}", "title=English (Original)",
             f"-metadata:s:a:{new_index}", "title=English (Clean)",
             f"-metadata:s:a:{new_index}", "language=" + audio[index].get("tags", {}).get("language", "eng")]
    for k, i in enumerate(kept):
        # Preserve other disposition bits, but prevent another default.
        disposition = audio[i].get("disposition", {})
        flags = "+".join(key for key, value in disposition.items() if value and key != "default") or "0"
        args += [f"-disposition:a:{k}", flags]
    args += [f"-disposition:a:{new_index}", "default", "-max_muxing_queue_size", "9999"]
    if testing:
        args += ["-t", "60"]
    args += [str(output_path)]
    return args, source, index, clean


def create_clean_video_command(input_path, output_path, mute_list=None, testing=False,
                               ffmpeg_path="ffmpeg ", mute_list_file=None):
    """Return a displayable command for legacy callers; execution uses argv."""
    import shlex
    output_path = Path(output_path)
    if mute_list_file is None:
        mute_list_file = output_path.with_name(output_path.stem+"_MUTE.txt")
        format_mute_list(mute_list, mute_list_file)
    args, _, _, _ = _clean_video_args(input_path, output_path,
        Path(mute_list_file).read_text(encoding="utf-8-sig"), ffmpeg_path, testing)
    return (subprocess.list2cmdline(args) if os.name == "nt" else shlex.join(args)), mute_list_file


def create_clean_video(input_path, output_path, mute_list=None, testing=False,
                       ffmpeg_path="ffmpeg ", del_mute_list_after=False, mute_list_file=None):
    """Build and probe a sibling temporary file before publishing any output."""
    import tempfile
    input_path, output_path = Path(input_path), Path(output_path)
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Use a separate output path; never overwrite an input directly")
    if mute_list_file is None:
        if mute_list is not None:
            mute_list_file = output_path.with_name(output_path.stem+"_MUTE.txt")
            format_mute_list(mute_list, mute_list_file)
        else:
            mute_list_file = check_for_mute_list(input_path)
    if mute_list_file is None:
        raise ValueError("No mute list provided")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".cleanvid-", suffix=output_path.suffix, dir=output_path.parent)
    os.close(fd)
    tmp = Path(name)
    tmp.unlink()  # ffmpeg -n requires an absent destination
    normalized_script = None
    try:
        args, source, index, previous_clean = _clean_video_args(
            input_path, tmp, Path(mute_list_file).read_text(encoding="utf-8-sig"), ffmpeg_path, testing)
        # Windows has a bounded command line. For long filters use a
        # temporary normalized script, never modify the saved mute list.
        k = args.index("-filter_complex")
        if len(subprocess.list2cmdline(args)) > 24000:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8",
                                             dir=output_path.parent, delete=False) as f:
                f.write(args[k+1])
                normalized_script = Path(f.name)
            args[k:k+2] = ["-filter_complex_script", str(normalized_script)]
        subprocess.run(args, check=True)
        if not file_exists(tmp):
            raise ValueError("FFmpeg produced an empty or truncated file")
        result = get_ffprobe_json(tmp)
        source_streams = source["streams"]
        output_streams = result.get("streams", [])
        original_audio = [s for s in source_streams if s["codec_type"] == "audio"]
        audio = [s for s in output_streams if s["codec_type"] == "audio"]
        if len(audio) != len(original_audio)-len(previous_clean)+1:
            raise ValueError("Unexpected audio stream count")
        keep = [s for i,s in enumerate(original_audio) if i not in previous_clean]
        if [s["codec_name"] for s in audio[:-1]] != [s["codec_name"] for s in keep]:
            raise ValueError("Original audio codecs changed")
        if audio[-1].get("tags", {}).get("title") != "English (Clean)" or not audio[-1].get("disposition", {}).get("default"):
            raise ValueError("Clean track is not marked default")
        if any(s.get("disposition", {}).get("default") for s in audio[:-1]):
            raise ValueError("Multiple default audio tracks")
        if audio[-1].get("channels") != original_audio[index].get("channels"):
            raise ValueError("Clean audio channel count changed")
        def nonaudio(streams):
            return [(s["codec_type"], s.get("codec_name")) for s in streams if s["codec_type"] != "audio"]
        if nonaudio(source_streams) != nonaudio(output_streams):
            raise ValueError("A non-audio stream changed or disappeared")
        expected = float(source["format"]["duration"])
        if testing:
            expected = min(expected, 60)
        if abs(float(result["format"]["duration"])-expected) > 1:
            raise ValueError("Output duration differs from input")
        subprocess.run([str(ffmpeg_path).strip().strip('"'), "-nostdin", "-v", "error", "-xerror",
                        "-i", str(tmp), "-map", f"0:a:{len(audio)-1}", "-f", "null", "-"], check=True)
        os.replace(tmp, output_path)
    finally:
        if tmp.exists():
            tmp.unlink()
        if normalized_script and normalized_script.exists():
            normalized_script.unlink()
    if del_mute_list_after:
        Path(mute_list_file).unlink()


def get_length(filename, ffprobe_path=r"ffprobe"):
    command = [str(ffprobe_path), "-v", "error", "-show_entries",
               "format=duration", "-of",
               "default=noprint_wrappers=1:nokey=1", str(filename)]
    print(" ".join(command))
    result = subprocess.run(command,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    try:
        valid_float = VALID_FLOAT_REGEX.match(result.stdout.decode()).group(0)
    except AttributeError:
        # If match fails (None has no attribute group)
        print(f"Error getting length for {filename}. Output: {result.stdout.decode()}")
        # Fallback or re-raise with better message
        raise ValueError(f"Could not determine length for {filename}")
        
    return float(valid_float)

def get_ffprobe_json(filename, ffprobe_path=r"ffprobe"):
    command = [str(ffprobe_path), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-show_error",
               str(filename)]
    print(" ".join(command))
    result = subprocess.run(command,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    # trim to end of json
    data = result.stdout.decode()
    data = data[:data.rfind("}")+1]
    return json.loads(data)

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
    
def generate_gcs_uri(source_path, bucket_name=None):
    """Generate the GCS URI for a file, matching the hash convention."""
    import hashlib
    import Global_Config
    
    bucket_name = bucket_name or Global_Config.BUCKET_NAME
    
    destination = Path(source_path).name
    destination = re.sub(r"[#\[\]*?]", "_", destination)
    
    # Hash destination to match main convention
    hash_val = hashlib.md5(destination.encode()).hexdigest()[:10]
    destination = f"{destination[:9]} + {hash_val}"
    
    return f"gs://{bucket_name}/{destination}"

if __name__=="__main__":
    audio_encoding_test()
    #ga = google_api(**config)
    #ga.resume_operation(config.operation_path)
