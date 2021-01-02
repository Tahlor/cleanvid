import sys
import pickle
import traceback
from pathlib import Path
from google.protobuf import json_format
from google.longrunning import operations_pb2
from google.api_core.operation import from_gapic

# Speech API
from google.cloud import speech_v1p1beta1 as speech_v1
from google.cloud.speech_v1p1beta1.proto import cloud_speech_pb2
#from google.cloud.speech_v2 import cloud_speech_pb2

# Video Intelligence API
from google.cloud.videointelligence_v1p3beta1.proto import video_intelligence_pb2
from google.cloud import videointelligence_v1p3beta1 as video_v1

from datetime import datetime
from time import sleep
import json
import os
from easydict import EasyDict as edict
from configparser import ConfigParser, SectionProxy

def clean_dict(d):
    for key in d:
        if isinstance(d[key], str):
            d[key] = d[key].replace('"',"")
            # if d[key].lower() == "False":
            #     d[key] = False
            # elif d[key].lower() == "True":
            #     d[key] = True

            print(d[key])
        elif isinstance(d[key], (ConfigParser,dict,SectionProxy)):
            clean_dict(d[key])

def process_config(path="./config"):
    config = ConfigParser()
    config.read(path)

    config.getboolean('main', 'require_api_confirmation') # require confirmation before performing a billed process
    config.getboolean('main', 'testing')

    if sys.platform=="win32":
        config["main"]["credential_path"] = str((Path(os.getcwd())  / Path(config["main"]["credential_path"].replace("/","\\").replace('"',""))).resolve())
        print(config["main"]["credential_path"])
        config['main']['ffmpeg_path'] = r"C:\ffmpeg-4.2.2-win64-static\ffmpeg-4.2.2-win64-static\bin\ffmpeg.exe"
        clean_dict(config)
    else:
        config['main']['ffmpeg_path'] = r"/usr/bin/ffmpeg"

    #video_path = ""J:\Media\Videos\Misc Videos\msc\Hillbilly.Elegy.2020.1080p.WEBRip.x265-RARBG\Hillbilly.Elegy.2020.1080p.WEBRip.x265-RARBG.mp4""

    my_config = {s: dict(config.items(s)) for s in config.sections()}

    # Ignore sections??? WHY?
    for s in config.sections():
        my_config.update(config.items(s))
    my_config = edict(my_config)

    return my_config

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

class google_speech_api:

    def __init__(self,
                 credential_path,
                 codec="flac",
                 sample_rate=44100,
                 require_api_confirmation=True,
                 api="speech", # speech, video
                 **kwargs
                 ):
        self.swears = parse_swears()
        self.codec = codec
        self.sample_rate = sample_rate
        self.api = api
        if api=="speech":
            self.speech_client = speech_v1.SpeechClient()
        elif api=="video":
            self.video_client = video_v1.VideoIntelligenceServiceClient()

        self.require_api_confirmation = require_api_confirmation
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credential_path

        self.speech_config = {
            "enable_word_time_offsets": True,
            "language_code": "en-US",
            "model": "video",  # default OR video audio recognition, video is more expensive
            "max_alternatives": 2,
            "profanity_filter": False
        }


    def serialize_operation(self, future, name):
        operation = future.operation
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Convert operation protobuf message to JSON-formatted string
        operation_json = json_format.MessageToJson(operation)
        json.dump(operation_json, Path(f"./data/google_api_responses/{name}_{now}.operation").open("w"))
        return operation_json

    def serialize_response(self, response, name):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        operation_json = json_format.MessageToJson(response)
        json.dump(operation_json, Path(f"./data/google_api_responses/{name}_{now}.response").open("w"))

    def restore_operation(self, json_path):
        # Convert JSON-formatted string to proto message
        operation_json = json.load(Path(json_path).open())
        operation = json_format.Parse(operation_json, operations_pb2.Operation())

        # load operation from backing store
        future = from_gapic(
            operation,
            self.speech_client.transport._operations_client,
            cloud_speech_pb2.LongRunningRecognizeResponse,
            metadata_type=cloud_speech_pb2.LongRunningRecognizeMetadata
        )

        return future

    def get_response(self, operation=None, name=None):
        if operation is None:
            operation = self.restore_operation(Path(f"./data/google_api_responses/{name}.operation"))
        done = False

        while not done:
            print("Waiting for response...")
            try:
                response = operation.result(timeout=30)
                done = True
            except Exception as e:
                print(f"No response...trying again {operation.metadata.progress_percent}%")
                if False:
                    traceback.print_exc()

            sleep(10)

       # Save the response!
        try:
            self.serialize_response(response, name=name)
        except:
            traceback.print_exc()
        return response

    def process_speech(self, storage_uri, name=None, response=None):
        if name is None:
            name = Path(storage_uri).stem

        if response is None:
            if self.api == "speech":
                operation = self.create_speech_operation(storage_uri=storage_uri, )
            elif self.api == "video":
                operation = self.create_video_speech_operation(storage_uri=storage_uri, )
            self.serialize_operation(operation, name=name)
            response = self.get_response(operation, name=name)
        else:
            response = self.load_response(response)
        
        mute_list, transcript = self.create_mute_list_from_response(response)
        pickle.dump({"mute_list": mute_list, "transcript": transcript},
                    Path(f"./data/mute_lists/{name}.pickle").open("wb"))
        return mute_list, transcript

    def process_adult_content(self, storage_uri, name=None, response=None):
        if name is None:
            name = Path(storage_uri).stem

        if response is None:
            operation = self.detect_explicit_content(storage_uri=storage_uri)
            self.serialize_operation(operation, name=name)
            response = self.get_response(operation, name=name)
        else:
            response = self.load_response(response)

        skip_list = self.create_skip_list(response)
        pickle.dump(skip_list,
                    Path(f"./data/mute_lists/{name}.pickle").open("wb"))
        return skip_list

    def create_skip_list(self, response):
        """ Create a list of tuples

        Args:
            response: A video response object

        Returns:
            list of tuples: [[start_skip, end_skip], ...]
        """
        pass

    def create_speech_operation(self, storage_uri, name=None):
        """
        Print start and end time of each word spoken in audio file from Cloud Storage
        https://cloud.google.com/speech-to-text/docs/basics#select-model

        # storage_uri = 'gs://cloud-samples-data/speech/brooklyn_bridge.flac'

        Args:
          storage_uri URI for audio file in Cloud Storage, e.g. gs://[BUCKET]/[FILE]
        """

        # When enabled, the first result returned by the API will include a list
        # of words and the start and end time offsets (timestamps) for those words.
        # The language of the supplied audio

        config = self.speech_config.copy()
        if self.codec == "flac":
            config.update({"encoding": speech_v1.enums.RecognitionConfig.AudioEncoding.FLAC})
        elif self.codec == "mp3":
            config.update({
                "sample_rate_hertz": self.sample_rate,
                "encoding": speech_v1.enums.RecognitionConfig.AudioEncoding.MP3,
                })

        audio = {"uri": storage_uri}

        # Use confirmation
        if self.require_api_confirmation:
            confirmation = input(f"Really recognize speech in {storage_uri}? (Y/n) ")
            if confirmation.lower() != "y":
                return

        operation = self.speech_client.long_running_recognize(config, audio)
        return operation

    def create_mute_list_from_response(self, response):
        print(u"Waiting for operation to complete...")

        # The first result includes start and end time word offsets
        mute_list = []
        results = response.results
        transcript = []
        for result in results:
            for alternative in result.alternatives:
                for word in alternative.words:
                    if word.word in self.swears:
                        start = word.start_time.seconds + word.start_time.nanos*10**-9
                        end   = word.end_time.seconds + word.end_time.nanos*10**-9
                        mute_list.append((start, end))
            phrase = result.alternatives[0].transcript
            if phrase:
                transcript.append(phrase)
        return mute_list, transcript

    def resume_operation(self, name):
        response = self.get_response(name=name)
        mute_list, transcript = self.create_mute_list_from_response(response)
        return mute_list

    def load_response(self, name):
        json_path = f"./data/google_api_responses/{name}.response"
        response_json = json.load(Path(json_path).open("r"))
        if self.api=="speech":
            response = json_format.Parse(response_json, cloud_speech_pb2.LongRunningRecognizeResponse())
        elif self.api=="video":
            response = json_format.Parse(response_json, video_intelligence_pb2.AnnotateVideoResponse())
        return response

    def detect_explicit_content(self, storage_uri, segments=None):
        features = [video_v1.enums.Feature.EXPLICIT_CONTENT_DETECTION]
        context = video_v1.types.VideoContext(segments=segments)

        print(f'Processing video "{storage_uri}"...')
        operation = self.video_client.annotate_video(
            input_uri=storage_uri,
            features=features,
            video_context=context,
        )
        return operation

    def create_video_speech_operation(self, storage_uri, segments=None):
        features = [video_v1.enums.Feature.SPEECH_TRANSCRIPTION]
        config = video_v1.types.SpeechTranscriptionConfig(
            **self.speech_config,
        )

        context = video_v1.VideoContext(
            segments=segments,
            speech_transcription_config=config,
        )

        print(f'Processing video "{storage_uri}"...')
        operation = self.video_client.annotate_video(
            input_uri=storage_uri,
            features=features,
            video_context=context,
        )
        return operation


def parse_swears(swears="swears.txt"):
    with open(swears) as f:
        lines = [line.rstrip('\n').split("|")[0] for line in f]
    return lines

def test_load_response():
    # Load old response
    config = process_config()
    ga = google_speech_api(**config)
    response = ga.load_response(config.response_path)
    mute_list, transcript = ga.create_mute_list_from_response(response)
    print(response.results)
    print(mute_list)

def test_resume_op():
    config = process_config()
    ga = google_speech_api(**config)
    ga.resume_operation(config.load_operation_path)

def test():
    config = process_config()
    ga = google_speech_api(**config)
    mute_list, transcript = ga.process_speech(config.uri)

if __name__=="__main__":
    config = process_config("./config_hill")
    ga = google_speech_api(**config)
    ga.resume_operation(config.operation_path)
