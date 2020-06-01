import dill
import numpy as np
import re
import os, sys
import delegator
from google.cloud import speech_v1
import ffmpeg
from pathlib import Path
import utils
import pickle

SAMPLE_RATE = 44100
CODEC = "mp3"

# Add clean audio channel though actually
def create_clean_video(input_path, mute_list, output_path, testing=False):
    output_ext = Path(input_path).suffix

    command = f"""ffmpeg -y -i "{input_path}" -c:v copy -af "{",".join(mute_list)}" """ + \
              f"""-c:a aac -ac 2 -ab 224k -ar 44100 "{str(Path(output_path).with_suffix(output_ext))}" """

    testing = "-to 00:01:00" if testing else ""
    command = f"""ffmpeg -y -i "{input_path}" -map 0:v:0 -c:v copy  """ + \
              f""" -filter_complex "[a:0]{",".join(mute_list)}[a]" {testing}""" + \
              f""" -metadata:s:a:0 title="Clean" -metadata:s:a:1 title="Normal" -map "[a]" -c:a:0 aac -map 0:a -c:a:1 copy  """ +\
              f""" "{str(Path(output_path).with_suffix(output_ext))}" """

    test = """ffmpeg -y -i "/media/taylor/Data/Linux/Github/personal_projects/cleanvid/vids/Richard Jewell/Richard.Jewell.2019.720p.mp4" -map 0:v:0 -c:v copy -filter_complex "[a:0]volume=enable='between(t,40,42)':volume=0,volume=enable='between(t,44,46)':volume=0[a]" -to 00:01:00 -metadata:s:a:0 title="One" -metadata:s:a:1 title="Two" -map [a] -c:a:0 aac -map 0:a -c:a:1 copy "OUTPUT.mp4"  """
    """
    -y – A global option to overwrite the output file if it already exists.
    -map 0:v – Designate the video stream(s) from the first input as a source for the output file.
    -c:v copy – Stream copy the video. This just muxes the input to the output. No re-encoding occurs.
    -map 0:a – Designate the audio stream(s) from the first input as a source for the output file.
    -c:a copy – Stream copy the audio. This just muxes the input to the output. No re-encoding occurs.
    -strict -2 -c:a aac – Use the native FFmpeg AAC audio encoder. -strict -2 is required as a way that you acknowledge that the encoder is designated as experimental. It is not a great encoder, but it is not too bad at higher bitrates.

    """

    #"ffmpeg -i video -c:v copy -af volume=0:enable='between(t,60,100)+between(t,330,370)+between(t,465,541.3)' out.mp4"

    print(command)
    ffmpegResult = delegator.run(command,
                                  block=True)
    if (ffmpegResult.return_code != 0) or (not os.path.isfile(output_path)):
        print(ffmpegResult.err)
        raise ValueError('Could not process %s' % (input_path))


def create_mute_list_old(time_list):
    """

    Args:
        subs (tuple): a list of tuples (start,end)

    Returns:

    """

    muteTimeList = []
    for timePair in time_list:
        lineStart = (timePair[0].hour * 60.0 * 60.0) + (timePair[0].minute * 60.0) + timePair[0].second + (
                    timePair[0].microsecond / 1000000.0)
        lineEnd = (timePair[1].hour * 60.0 * 60.0) + (timePair[1].minute * 60.0) + timePair[1].second + (
                    timePair[1].microsecond / 1000000.0)
        muteTimeList.append("volume=enable='between(t," + format(lineStart, '.3f') + "," + format(lineEnd, '.3f') + ")':volume=0")

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
        muteTimeList.append("volume=enable='between(t," + format(lineStart, '.3f') + "," + format(lineEnd, '.3f') + ")':volume=0")
    return muteTimeList

def split_video(path, name=None, length=3600, start_time="00:00:00", end_time="99:59:59"):
    """ Split video into 1 hour segments

    """
    # get total length
    #""
    #"ffmpeg -i myfile.avi"
    if name is None:
        name = path.stem

    output = f"./temp/{name}/%03d"
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    # Keep audio stream in same codec
    # command = f"""ffmpeg -i "{path}" -f segment -segment_time {length} -ss {start_time} -to {end_time}  -vn -acodec copy {output_str}"""
    # "ffmpeg -i "/media/taylor/Data/Linux/Github/personal_projects/cleanvid/vids/Richard Jewell/Richard.Jewell.2019.720p.mp4" -f segment -segment_time 14 -ss 00:05:00 -to 00:05:13 -vn "./temp/TEMP%03d.mp3""
    output_str = f'"{output}.{CODEC}"'
    if CODEC == "flac":
        codec_command = "-c:a flac "
    elif CODEC == "mp3":
        codec_command =  f"-ar {SAMPLE_RATE} "
    else:
        codec_command = ""

    command = f"""ffmpeg -i "{path}" -f segment -segment_time {length} -ss {start_time} -to {end_time} {codec_command} -af dynaudnorm -ac 1 -vn {output_str}"""
    # -ac 1 : one audio channel
    # -vn   : exclude video

    print(command)
    ffmpegResult = delegator.run(command, block=True)
    return ffmpegResult, output


def upload_to_cloud(source, destination, overwrite=False):
    from google.cloud import storage
    # GO HERE: https://console.cloud.google.com/apis/credentials/serviceaccountkey
    # Choose project, select "owner" account

    #storage_client = storage.Client.from_service_account_json("./credentials/credentials.json")
    #storage_client = storage.Client()

    # creds = authorize("./credentials/credentials.json", "./credentials/token.pickle")
    # from googleapiclient.discovery import build
    # storage_client = build('storage', version="v1p1beta", credentials=creds)

    storage_client = storage.Client()
    #bucket = storage_client.create_bucket("remove_profanity_from_movie_project")
    #buckets = list(storage_client.list_buckets())
    # Browse Bucket: https://console.cloud.google.com/storage/browser/remove_profanity_from_movie_project?forceOnBucketsSortingFiltering=false&project=speech-to-text-1590881833772
    bucket = storage_client.get_bucket("remove_profanity_from_movie_project")
    #     bucket = storage_client.bucket(bucket_name)
    destination = re.sub("[#\[\]*?]", "_", destination)

    if (not storage.Blob(bucket=bucket, name=destination).exists(storage_client)) or overwrite:
        print(f"Uploading {destination}...")
        blob = bucket.blob(f'{destination}')
        blob.upload_from_filename(str(source))
    else:
        print(f"{destination} already uploaded")
    return destination

def main(path,
         testing=True,
         length=1000000, # how many seconds
         start_time="0",
         end_time="99:59:59",
         overwrite=True):

    ext = f".{CODEC}"
    name = Path(path).stem

    if testing:
        length = 14
        start_time = "00:00:45"
        end_time = "00:00:58"
        overwrite = True # don't overwrite if already uploaded
        name = Path(path).stem + "_testing"

    # # Testing #2
    # if True:
    #     length = 14
    #     start_time = "00:00:45"
    #     overwrite = True # don't overwrite if already uploaded
    #     name = Path(path).stem + "_testing"

    # split
    main_path = Path(f"./temp/{name}/000{ext}")
    if not Path(main_path).exists():
        result, _ = split_video(path, name, length=length, start_time=start_time, end_time=end_time)

    print("Done splitting...")
    api = utils.google_api(codec=CODEC, sample_rate=SAMPLE_RATE)

    # upload
    #for vid in Path(main_path).parent.glob(f"*{ext}"):
    vid = Path(main_path)
    destination = upload_to_cloud(vid, str(Path(vid.parent.name) / vid.name), overwrite=overwrite)
    uri = f"gs://remove_profanity_from_movie_project/{destination}"
    proto_mute_list, transcript = api.process(uri, name=name)

    final_mute_list = create_mute_list(proto_mute_list)

    if testing:
        final_mute_list = create_mute_list([[0,1]])

    # Update
    output = path.parent / (path.stem + "_clean" + path.suffix)
    create_clean_video(path, final_mute_list, output, testing=testing)

def process_old_response(path, response="Richard.Jewell.2019.720p00", name=None):
    if name is None:
        name = response.split("000")[0]
    if response.endswith(".response"):
        response = response[:-len(".response")]

    ga = utils.google_api()
    response = ga.load_response(response)
    mute_list, transcript = ga.create_mute_list_from_response(response)
    pickle.dump({"mute_list": mute_list, "transcript": transcript}, Path(f"./data/mute_lists/{name}.pickle").open("wb"))
    print(transcript)
    final_mute_list = create_mute_list(mute_list)
    output = path.parent / (path.stem + "_clean" + path.suffix)
    create_clean_video(path, final_mute_list, output)


if __name__=='__main__':
    #path = Path("/media/taylor/Data/Linux/Github/personal_projects/cleanvid/Donnie Darko[2001] (DVD).avi")
    path = Path("/media/taylor/Data/Linux/Github/personal_projects/cleanvid/vids/Richard Jewell/Richard.Jewell.2019.720p.mp4")

    # Do new proccess
    if False:
        main(path, overwrite=False, testing=True)
    else:
        # Process old response
        response = "Richard.Jewell.2019.720p000_2020-06-01 00:40:30_2020-06-01 01:00:45"
        response = "Richard.Jewell.2019.720p000_2020-06-01 11:11:25"
        process_old_response(path, response=response)

    ## AAC/FLAC - upload as WAV??