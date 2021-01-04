import re
import utils
from pathlib import Path
from datetime import datetime
from time import sleep
import json
import os
import pickle
import traceback
from easydict import EasyDict as edict

from google.protobuf import json_format
from google.longrunning import operations_pb2
from google.api_core.operation import from_gapic

# Speech API
from google.cloud import speech_v1p1beta1 as speech_v1
from google.cloud.speech_v1p1beta1.proto import cloud_speech_pb2

# Video Intelligence API
from google.cloud import videointelligence

# Response
#from google.cloud.videointelligence_v1p3beta1.proto import video_intelligence_pb2 as _video_intelligence # the old one
from google.cloud.videointelligence_v1p3beta1.types import video_intelligence as _video_intelligence
from google.cloud.videointelligence_v1.types import video_intelligence as _video_intelligence1
from google.cloud import videointelligence_v1p3beta1 as video_v1
# from google.cloud.videointelligence_v1p1beta1.proto import video_intelligence_pb2
# from google.cloud import videointelligence_v1p1beta1 as video_v1

#https://cloud.google.com/video-intelligence/docs/transcription#video_speech_transcription_gcs-python


class google_speech_api:

    def __init__(self,
                 credential_path,
                 codec="flac",
                 sample_rate=44100,
                 require_api_confirmation=True,
                 api="speech",  # speech, video
                 **kwargs
                 ):
        self.swears = utils.parse_swears()
        self.codec = codec
        self.sample_rate = sample_rate
        self.api = api

        self.speech_config = {
            "enable_word_time_offsets": True,
            "language_code": "en-US",
            "max_alternatives": 2,
            "profanity_filter": False
        }

        if api == "speech":
            self.speech_client = self.client = speech_v1.SpeechClient()
            self.speech_config["model"] = "video"  # default OR video, video-style recognition is more expensive
        elif api == "video":
            self.video_client = self.client = video_v1.VideoIntelligenceServiceClient()

        self.require_api_confirmation = require_api_confirmation
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credential_path

    def serialize_operation(self, future, name):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # if isinstance(future, _video_intelligence.AnnotateVideoResponse):
        #     operation = future._pb
        # else:
        #     operation = future.operation
        operation = future.operation
        # Convert operation protobuf message to JSON-formatted string
        operation_json = json_format.MessageToJson(operation)
        json.dump(operation_json, Path(f"./data/google_api/{name}_{now}.operation").open("w"))
        return operation_json

    def serialize_response(self, response, name):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            operation_json = json_format.MessageToJson(response)
        except: # video_intelligence.AnnotateVideoResponse
            response = response._pb
            operation_json = json_format.MessageToJson(response)
        json.dump(operation_json, Path(f"./data/google_api/{name}_{now}.response").open("w"))
        return response

    def restore_operation(self, json_path):
        """ UNTESTED AND PROBABLY NOT WORKING

        Args:
            json_path:

        Returns:

        """
        # Convert JSON-formatted string to proto message
        operation_json = json.load(Path(json_path).open())
        operation = json_format.Parse(operation_json, operations_pb2.Operation())

        # load operation from backing store
        if self.api=="speech":
            future = from_gapic(
                operation,
                self.client.transport._operations_client,
                cloud_speech_pb2.LongRunningRecognizeResponse,
                metadata_type=cloud_speech_pb2.LongRunningRecognizeMetadata
            )
        else:
            future = from_gapic(
                operation,
                self.client.transport.operations_client,
                _video_intelligence.AnnotateVideoResponse,
                #metadata_type=_video_intelligence.Ann
            )

        # operation = video_client.annotate_video(
        #     path, features=features, video_context=video_context
        # )
        # print("\nProcessing video for speech transcription.")
        # result = operation.result(timeout=600)
        # annotation_results = result.annotation_results[0]

        return future

    def get_response(self, operation=None, name=None):
        if operation is None:
            operation = self.restore_operation(Path(f"./data/google_api/{name}.operation"))
        done = False

        while not done:
            print("Waiting for response...")
            try:
                response = operation.result(timeout=60)
                done = True
            except Exception as e:
                try:
                    if "progress_percent" in operation.metadata.__dict__:
                        print(f"No response...trying again {operation.metadata.progress_percent}%")
                    else:
                        percent = operation.metadata.annotation_progress._pb[0].progress_percent
                        print(f"No response...trying again {percent}%")
                except:
                    print("Problem with metadata")
                    traceback.print_exc()
            sleep(10)

        # Save the response!
        try:
            response = self.serialize_response(response, name=name) # take the _pb attribute as needed
        except:
            traceback.print_exc()
        return response

    def process_speech(self, storage_uri, name=None, response=None, operation=None, path=None):
        if name is None:
            name = Path(storage_uri).stem

        if response is None:
            if operation is None:
                if self.api == "speech":
                    operation = self.create_speech_operation(storage_uri=storage_uri, )
                elif self.api == "video":
                    operation = self.create_video_speech_operation(storage_uri=storage_uri, )
                else:
                    print(self.api)
                    raise Exception("Unknown API")
                self.serialize_operation(operation, name=name)
            response = self.get_response(operation, name=name)
        else:
            response = self.load_response(response)
        path = Path(f"./data/mute_lists") if path is None else Path(path)
        mute_list, transcript = self.create_mute_list_from_response(response)
        pickle.dump({"mute_list": mute_list, "transcript": transcript},
                    (path / f"{name}.pickle").open("wb"))
        return mute_list, transcript

    def process_adult_content(self, storage_uri, name=None, response=None, path=None):
        if name is None:
            name = Path(storage_uri).stem

        if response is None:
            operation = self.detect_explicit_content(storage_uri=storage_uri)
            self.serialize_operation(operation, name=name)
            response = self.get_response(operation, name=name)
        else:
            response = self.load_response(response)

        skip_list = self.create_skip_list(response)

        path = Path(f"./data/skip_lists") if path is None else Path(path)
        pickle.dump(skip_list,
                    path / f"{name}.pickle".open("wb"))
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
                raise Exception("Did not agree to recognize speech")

        operation = self.speech_client.long_running_recognize(config, audio)
        return operation

    def create_mute_list_from_response(self, response):
        def convert_to_seconds(word_time):
            # word.start_time
            start = word_time.seconds + word_time.nanos * 10 ** -9
            return start

        print(u"Waiting for operation to complete...")
        strip_punctuation = re.compile('[^-a-zA-Z \']+')

        # The first result includes start and end time word offsets
        mute_list = []
        if "Annotate" in str(type(response)):
            results = [x for x in response.annotation_results[0].speech_transcriptions]
        else:
            results = response.results
        transcript = []
        cleaned_transcript = []
        for result in results:
            for i,alternative in enumerate(result.alternatives):
                previous_word = previous_start_time = ""
                for word in alternative.words:
                    _word = strip_punctuation.sub("", word.word).lower()
                    compound_phrase = f"{previous_word} {_word}".strip()
                    if compound_phrase in self.swears and previous_start_time:
                        end = convert_to_seconds(word.end_time)
                        mute_list.append((previous_start_time, end))
                    elif _word in self.swears:
                        start = convert_to_seconds(word.start_time)
                        end = convert_to_seconds(word.end_time)
                        mute_list.append((start, end))
                        if i == 0:
                            cleaned_transcript.append(word.word[0] + "*"*(len(_word)-1) )
                    elif i == 0:
                        cleaned_transcript.append(word.word)

                    previous_word = _word
                    previous_start_time = convert_to_seconds(word.start_time)

        phrase = result.alternatives[0].transcript
        if phrase:
            transcript.append(phrase)
        print(" ".join(cleaned_transcript))
        return mute_list, transcript

    def resume_operation(self, name):
        response = self.get_response(name=name)
        mute_list, transcript = self.create_mute_list_from_response(response)
        return mute_list

    def load_response(self, json_path):
        response_json = json.load(Path(json_path).open("r"))
        if self.api == "speech":
            response = json_format.Parse(response_json, cloud_speech_pb2.LongRunningRecognizeResponse())
        elif self.api == "video":
            response = json_format.Parse(response_json, _video_intelligence.AnnotateVideoResponse()._pb)

        return response

    def load_operation(self, json_path):
        operation = json.load(Path(json_path).open("r"))
        return operation

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

    def create_video_speech_operation1(self,  storage_uri, **kwargs):
        config = self.speech_config.copy()

        audio = {"uri": storage_uri}

        # Use confirmation
        if self.require_api_confirmation:
            confirmation = input(f"Really recognize speech in {storage_uri}? (Y/n) ")
            if confirmation.lower() != "y":
                raise Exception("Did not agree to recognize speech")

        operation = self.client.annotate_video(config, audio)
        return operation

    def create_video_speech_operation2(self, storage_uri, segments=None):
        features = [video_v1.enums.Feature.SPEECH_TRANSCRIPTION]
        config = video_v1.types.SpeechTranscriptionConfig(**self.speech_config)

        context = video_v1.types.VideoContext(
            segments=segments,
            speech_transcription_config=self.speech_config,
        )

        print(f'Processing video "{storage_uri}"...')
        operation = self.video_client.annotate_video(
            input_uri=storage_uri,
            features=features,
            video_context=context,
        )
        return operation

    def create_video_speech_operation(self, *args, **kwargs):
        return self.create_video_speech_operation_from_model(*args, **kwargs)

    def create_video_speech_operation_from_model(self, storage_uri, *args, **kwargs): # i.e. copied and pasted from Google
        """Transcribe speech from a video stored on GCS."""
        from google.cloud import videointelligence
        video_client = videointelligence.VideoIntelligenceServiceClient()
        features = [videointelligence.Feature.SPEECH_TRANSCRIPTION]

        config = videointelligence.SpeechTranscriptionConfig(
            language_code="en-US",
            enable_automatic_punctuation=True,
            #enable_word_time_offsets=True,
            max_alternatives=2
        )
        video_context = videointelligence.VideoContext(speech_transcription_config=config)
        operation = video_client.annotate_video(
            request={
                "features": features,
                "input_uri": storage_uri,
                "video_context": video_context,
            }
        )

        # Use confirmation
        if self.require_api_confirmation:
            confirmation = input(f"Really recognize speech in {storage_uri}? (Y/n) ")
            if confirmation.lower() != "y":
                raise Exception("Did not agree to recognize speech")

        print("\nProcessing video for speech transcription.")
        return operation