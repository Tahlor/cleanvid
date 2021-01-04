import re
import os, sys
import delegator
from google.cloud import storage
import google_api
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
        self.speech_api = google_api.google_speech_api(codec=self.codec,
                                                  sample_rate=self.sample_rate,
                                                  credential_path=self.credential_path,
                                                  **kwargs)


    def upload_to_cloud(self, source, destination, overwrite=False):
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
             overwrite_cloud=True,
             overwrite_local=True,
             api="video",
             operation=None,
             **kwargs):

        ext = f".{self.codec}"
        name = Path(path).stem

        if testing and False:
            length = 14
            # start_time = "00:00:45"
            # end_time = "00:00:58"
            # start_time = "01:23:00"
            # end_time = "01:23:13"
            start_time = "00:04:32"
            end_time = "00:04:45"
            overwrite_local = overwrite_cloud = True
            name += "_testing"
            output_path = Path(f"./temp/{name}")
            output_path.mkdir(exist_ok=True, parents=True)
            result, path = utils.trim_video(input=path, output=output_path, start=start_time, end=end_time)

        processed_path = Path(f"./temp/{name}")
        processed_path.mkdir(exist_ok=True, parents=True)
        processed_path = processed_path / name
        # split - mostly for testing!
        process = utils.process_video if api == "video" else utils.process_audio

        if not Path(processed_path).exists():
            result, processed_path = process(path, processed_path, overwrite=overwrite_local, **kwargs)
        print("Done processing...")

        # upload
        #for vid in Path(main_path).parent.glob(f"*{ext}"):
        vid = Path(processed_path)
        destination = self.upload_to_cloud(vid, str(Path(vid.parent.name) / vid.name), overwrite=overwrite_cloud)
        uri = f"gs://remove_profanity_from_movie_project/{destination}"
        proto_mute_list, transcript = self.speech_api.process_speech(uri, name=name, operation=operation)

        final_mute_list = utils.create_mute_list(proto_mute_list)

        if testing:
            final_mute_list = utils.create_mute_list([[0,1]])

        # Update
        path = Path(path)
        output = path.parent / (path.stem + "_clean" + path.suffix)
        utils.create_clean_video(path, final_mute_list, output, testing=testing)

    def process_saved_operation(self, *args, operation, **kwargs):
        operation = self.speech_api.restore_operation(operation)
        return self.main(*args, operation=operation, **kwargs)

    def process_saved_response(self, video_path, response_path, name=None, output_path=None):
        # if name is None:
        #     name = Path(response_path)
        #     name = response_path.split("000")[0]
        # if name.endswith(".response"):
        #     name = name[:-len(".response")]
        video_path = Path(video_path)
        if output_path is None:
            output_path = Path(response_path).parent
        name = Path(response_path).stem
        response = self.speech_api.load_response(response_path)
        mute_list, transcript = self.speech_api.create_mute_list_from_response(response)
        pickle.dump({"mute_list": mute_list, "transcript": transcript}, (output_path / f"{name}.pickle").open("wb"))
        print(transcript)
        final_mute_list = utils.create_mute_list(mute_list)
        output = video_path.parent / (video_path.stem + "_clean" + video_path.suffix)
        utils.create_clean_video(video_path, final_mute_list, output)


if __name__=='__main__':
    #config = utils.process_config("testing_config.ini")
    config = utils.process_config("hillbilly")

    cp = CleanProfanity(**config)

    if "load_response_path" in config.keys() and config.load_response_path:
        # Process previous response
        cp.process_saved_response(config.video_path, response_path=config.load_response_path)
    elif "load_operation_path" in config.keys() and config.load_operation_path:
        cp.process_saved_operation(config.video_path,
                                    overwrite_cloud=config.overwrite.overwrite_cloud,
                                    overwrite_local=config.overwrite.overwrite_ffmpeg_files,
                                    testing=config.testing,
                                    blank_video=config.blank_video,
                                    operation=config.load_operation_path)
    else:
        # Do new proccess
        cp.main(config.video_path,
                overwrite_cloud=config.overwrite.overwrite_cloud,
                overwrite_local=config.overwrite.overwrite_ffmpeg_files,
                testing=config.testing,
                blank_video=config.blank_video)
