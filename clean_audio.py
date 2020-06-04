import re
import os, sys
import delegator
from google.cloud import storage
from pathlib import Path
import utils
import pickle

class CleanProfanity:
    def __init__(self,
                 credential_path,
                 ffmpeg_path="ffmpeg ",
                 codec=".mp3",
                 sample_rate=44100,
                 **kwargs
                 ):
        self.credential_path = credential_path
        self.ffmpeg_path = ffmpeg_path
        self.codec = codec
        self.sample_rate = sample_rate
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credential_path
        self.speech_api = utils.google_speech_api(codec=self.codec,
                                                  sample_rate=self.sample_rate,
                                                  credential_path=self.credential_path,
                                                  **kwargs)

    @staticmethod
    def create_clean_video(input_path, mute_list, output_path, testing=False, ffmpeg_path="ffmpeg "):
        output_ext = Path(input_path).suffix

        testing = "-to 00:01:00" if testing else ""
        command = f"""{ffmpeg_path} -y -i "{input_path}" -map 0:v:0 -c:v copy  """ + \
                  f""" -filter_complex "[a:0]{",".join(mute_list)}[a]" {testing}""" + \
                  f""" -metadata:s:a:0 title="Clean" language="eng" -metadata:s:a:1 title="Normal" -map "[a]" -c:a:0 aac -map 0:a -c:a:1 copy  """ +\
                  f""" "{str(Path(output_path).with_suffix(output_ext))}" """

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

    def split_audio(self, path, name=None, length=3600, start_time="00:00:00", end_time="99:59:59"):
        """ Split video into 1 hour segments

        """
        if name is None:
            name = path.stem

        output = f"./temp/{name}/%03d"
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        output_str = f'"{output}.{self.codec}"'
        if self.codec == "flac":
            codec_command = "-c:a flac "
        elif self.codec == "mp3":
            codec_command =  f"-ar {self.sample_rate} "
        else:
            codec_command = ""

        command = f"""{self.ffmpeg_path} -i "{path}" -f segment -segment_time {length} -ss {start_time} -to {end_time} {codec_command} -af dynaudnorm -ac 1 -vn {output_str}"""
        # -ac 1 : one audio channel
        # -vn   : exclude video

        print(command)
        ffmpegResult = delegator.run(command, block=True)
        return ffmpegResult, output

    def split_video(self, path, name=None, length=3600, start_time="00:00:00", end_time="99:59:59"):
        """ Split video into 1 hour segments

        """
        if name is None:
            name = path.stem

        output = f"./temp/{name}/%03d"
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        # if AVI, convert to MP4
        codec = ""
        codec_command = ""
        output_str = f'"{output}.{codec}"'


        command = f"""{self.ffmpeg_path} -i "{path}" -f segment -segment_time {length} -ss {start_time} -to {end_time} {codec_command} -af dynaudnorm -ac 1 {output_str}"""
        # -ac 1 : one audio channel
        # -vn   : exclude video

        print(command)
        ffmpegResult = delegator.run(command, block=True)
        return ffmpegResult, output


    def upload_to_cloud(source, destination, overwrite=False):
        # GO HERE: https://console.cloud.google.com/apis/credentials/serviceaccountkey
        # Choose project, select "owner" account

        storage_client = storage.Client()
        try:
            bucket = storage_client.create_bucket("remove_profanity_from_movie_project")
        except:
            pass

        # Browse Bucket: https://console.cloud.google.com/storage/browser/remove_profanity_from_movie_project?forceOnBucketsSortingFiltering=false&project=speech-to-text-1590881833772
        bucket = storage_client.get_bucket("remove_profanity_from_movie_project")
        destination = re.sub("[#\[\]*?]", "_", destination)

        if (not storage.Blob(bucket=bucket, name=destination).exists(storage_client)) or overwrite:
            print(f"Uploading {destination}...")
            blob = bucket.blob(f'{destination}')
            blob.upload_from_filename(str(source))
        else:
            print(f"{destination} already uploaded")
        return destination

    def main(self,
             path,
             testing=True,
             length=1000000, # how many seconds
             start_time="0",
             end_time="99:59:59",
             overwrite=True,
             api="video"):

        ext = f".{self.codec}"
        name = Path(path).stem

        if testing:
            length = 14
            start_time = "00:00:45"
            end_time = "00:00:58"
            overwrite = True # don't overwrite if already uploaded
            name = Path(path).stem + "_testing"

        # split - mostly for testing!
        # but we still need to either extract audio / reformat video as needed; if only profanity, could encode trivial video...?
        main_path = Path(f"./temp/{name}/000{ext}")
        split = self.split_audio if self.api == "speech" else self.split_video
        if not Path(main_path).exists():
            result, _ = self.split(path, name, length=length, start_time=start_time, end_time=end_time)
        print("Done splitting...")

        # upload
        #for vid in Path(main_path).parent.glob(f"*{ext}"):
        vid = Path(main_path)
        destination = self.upload_to_cloud(vid, str(Path(vid.parent.name) / vid.name), overwrite=overwrite)
        uri = f"gs://remove_profanity_from_movie_project/{destination}"
        proto_mute_list, transcript = self.speech_api.process_speech(uri, name=name)

        final_mute_list = utils.create_mute_list(proto_mute_list)

        if testing:
            final_mute_list = utils.create_mute_list([[0,1]])

        # Update
        output = path.parent / (path.stem + "_clean" + path.suffix)
        self.create_clean_video(path, final_mute_list, output, testing=testing)

    def process_saved_response(self, video_path, response_path, name=None):
        if name is None:
            name = response_path.split("000")[0]
        if response_path.endswith(".response"):
            response_path = response_path[:-len(".response")]

        response = self.speech_api.load_response(response_path)
        mute_list, transcript = self.speech_api.create_mute_list_from_response(response)
        pickle.dump({"mute_list": mute_list, "transcript": transcript}, Path(f"./data/mute_lists/{name}.pickle").open("wb"))
        print(transcript)
        final_mute_list = utils.create_mute_list(mute_list)
        output = video_path.parent / (video_path.stem + "_clean" + video_path.suffix)
        CleanProfanity.create_clean_video(video_path, final_mute_list, output)


if __name__=='__main__':
    config = utils.process_config()

    Stop
    cp = CleanProfanity(**config)

    if not config.response:
        # Do new proccess
        cp.main(config.video_path, overwrite=False, testing=config.testing)
    else:
        # Process previous response
        CleanProfanity.process_saved_response(config.video_path, response=config.load_response_path)

