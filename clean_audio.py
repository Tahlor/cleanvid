import tqdm
import argparse
import re
import os, sys
import delegator
from google.cloud import storage
BLOB_SIZE = 1 # 5 has worked previously
storage.blob._MAX_MULTIPART_SIZE = BLOB_SIZE * 1024* 1024 # 5 MB
storage.blob._DEFAULT_CHUNKSIZE = BLOB_SIZE * 1024* 1024 # 5 MB

import google_api
from pathlib import Path
import utils
import pickle

"""
Usage:
cd D:\Github\cleanvid
activate web
python clean_audio.py configs/my_config [--video PATH_TO_VIDEO]

video_path can be specified in the config or in the commandline call


try:
    options = parser.parse_args()
except:
    parser.print_help()
    sys.exit(0)
    
"""


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


    def upload_to_cloud(self, source, destination, overwrite=False, already_processed_okay=True):
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
        file_already_uploaded=False
        if (not storage.Blob(bucket=bucket, name=destination).exists(storage_client)) or overwrite:
            print(f"Uploading {destination}...")
            blob = bucket.blob(f'{destination}')
            blob.chunk_size = BLOB_SIZE * 1024 * 1024 # Set 5 MB (or less) blob size so slower networks don't timeout
            if False:
                blob.upload_from_filename(str(source))
            else:
                # Has TQDM progress
                while True:
                    try:
                        self.upload_blob(bucket, blob, source=source)
                        break
                    except:
                        pass
        else:
            print(f"{destination} already uploaded")
            if not already_processed_okay:
                raise Exception("Previously uploaded!")
            file_already_uploaded = True
        print("Done uploading")

        return destination, file_already_uploaded

    def upload_blob(self, bucket, blob, source):
        """
        upload_blob(storage.Client(), "bucket", "/etc/motd", "/path/to/blob.txt", "text/plain")

        Args:
            bucket_name:
            source:
            dest:
            content_type:

        Returns:

        """
        with open(source, "rb") as in_file:
            total_bytes = os.fstat(in_file.fileno()).st_size
            with tqdm.tqdm.wrapattr(in_file, "read", total=total_bytes, miniters=1, desc="upload to %s" % bucket.name) as file_obj:
                blob.upload_from_file(
                    file_obj,
                    size=total_bytes,
                )
                return blob

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
             uri=None,
             already_processed_okay=True,
             **kwargs):

        ext = f".{self.codec}"
        name = Path(path).stem

        if testing:
            length = 14
            # start_time = "00:00:45"
            # end_time = "00:00:58"
            # start_time = "01:23:00"
            # end_time = "01:23:13"
            start_time = "01:26:20"
            end_time = "01:26:34"
            overwrite_local = overwrite_cloud = True
            name += "_testing"
            uri = (Path(uri).parent / f"{Path(uri).name}_testing").with_suffix(Path(uri).suffix)

            output_folder = Path(f"./temp/{name}")
            output_folder.mkdir(exist_ok=True, parents=True)
            output_path = (output_folder / f"{name}{ext}").resolve()
            # This part doesn't work
            if not Path(output_path).exists():
                result, path = utils.trim_video(input=path, output=output_path, start=start_time, end=end_time, ffmpeg_path=self.ffmpeg_path)
            else:
                path = output_path

        processed_path = Path(f"./temp/{name}")
        processed_path.mkdir(exist_ok=True, parents=True)
        processed_path = (processed_path / f"{name}_processed{ext}").resolve()
        # split - mostly for testing!
        process = utils.process_video if api == "video" else utils.process_audio

        if (not utils.file_exists(processed_path)) or overwrite_local:
            result, processed_path = process(path, processed_path, overwrite=overwrite_local, ffmpeg_path=self.ffmpeg_path, **kwargs)
            print("File size:", os.path.getsize(processed_path))
        print("Done processing...")

        # upload
        #for vid in Path(main_path).parent.glob(f"*{ext}"):
        prefix = r"gs://remove_profanity_from_movie_project/"

        vid = Path(processed_path)
        if uri is not None and prefix in uri:
            uri_name = uri.replace(prefix, "")
        else:
            uri_name = str(Path(vid.parent.name)) / vid.name

        destination, file_already_uploaded = self.upload_to_cloud(vid, uri_name, overwrite=overwrite_cloud, already_processed_okay=already_processed_okay)
        if file_already_uploaded:
            cont = input("File already uploaded; continue with speech API process request? Y/n " )
            if cont.lower() != "y":
                return False

        uri = f"{prefix}{destination}"

        proto_mute_list, transcript = self.speech_api.process_speech(uri, name=name, operation=operation)

        final_mute_list = utils.create_mute_list(proto_mute_list)

        if testing:
            final_mute_list = utils.create_mute_list([[0,1]])

        # Update
        path = Path(path)
        output = path.parent / (path.stem + "_clean" + path.suffix)
        utils.create_clean_video(path, final_mute_list, output, testing=testing, ffmpeg_path=self.ffmpeg_path)
        return True

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
        if final_mute_list:
            utils.create_clean_video(video_path, final_mute_list, output, ffmpeg_path=self.ffmpeg_path)
        else:
            print("No profanity detected :/")

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('config', nargs='?', default='')
    parser.add_argument('--video', type=str, default='', help='Path to the video file.')
    parser.add_argument('--response', type=str, default='', help='Path to response file.')
    output_config = None
    opts = parser.parse_args()
    if not opts.config:
        opts.config = "configs/default_config"
        output_config = f"configs/{Path(opts.video).stem}"
    config, _config_parser = utils.process_config(opts.config, video_path=opts.video, response_path=opts.response)

    if not output_config is None:
        with open(output_config, 'w') as configfile:    # save
            _config_parser.write(configfile)


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
                                    operation=config.load_operation_path,
                                    uri=config.uri)
    else:
        # Do new proccess
        cp.main(config.video_path,
                overwrite_cloud=config.overwrite.overwrite_cloud,
                overwrite_local=config.overwrite.overwrite_ffmpeg_files,
                testing=config.testing,
                blank_video=config.blank_video,
                uri=config.uri)
