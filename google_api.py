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
import Global_Config

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
                 config=None,
                 **kwargs
                 ):
        self.swears = utils.parse_swears()
        self.subtitle_exceptions = utils.parse_subtitle_exceptions()
        self.codec = codec
        self.sample_rate = sample_rate
        self.api = api

        self.speech_config = {
            "enable_word_time_offsets": True,
            "language_code": "en-US",
            "max_alternatives": 2,
            "profanity_filter": False
        }

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(credential_path)

        if api == "speech":
            self.speech_client = self.client = speech_v1.SpeechClient()
            self.speech_config["model"] = "video"  # default OR video, video-style recognition is more expensive
        elif api == "video":
            self.video_client = self.client = video_v1.VideoIntelligenceServiceClient()

        self.require_api_confirmation = require_api_confirmation
        self.response_output_folder = config.api_response_root if config is not None else Path("./data/google_api")

    def upload_file(self, source_path, overwrite=True):
        """Upload a file to Google Cloud Storage.

        Args:
            source_path: Local path to the file to upload.
            overwrite: If True, overwrite existing blob in GCS.

        Returns:
            str: The GCS URI (gs://bucket/destination) of the uploaded file.
        """
        import hashlib
        import tqdm
        from google.cloud import storage

        BLOB_SIZE = 1  # MB
        storage.blob._MAX_MULTIPART_SIZE = BLOB_SIZE * 1024 * 1024
        storage.blob._DEFAULT_CHUNKSIZE = BLOB_SIZE * 1024 * 1024

        storage_client = storage.Client()
        try:
            bucket = storage_client.create_bucket(Global_Config.BUCKET_NAME)
        except Exception:
            bucket = storage_client.get_bucket(Global_Config.BUCKET_NAME)

        source_path = str(source_path)
        gcs_uri = utils.generate_gcs_uri(source_path)
        destination = gcs_uri.replace(f"gs://{Global_Config.BUCKET_NAME}/", "")

        blob_exists = storage.Blob(bucket=bucket, name=destination).exists(storage_client)
        if not blob_exists or overwrite:
            print(f"Uploading {destination}...")
            blob = bucket.blob(destination)
            blob.chunk_size = BLOB_SIZE * 1024 * 1024

            with open(source_path, "rb") as in_file:
                total_bytes = os.fstat(in_file.fileno()).st_size
                with tqdm.tqdm.wrapattr(
                    in_file, "read", total=total_bytes, miniters=1,
                    desc=f"upload to {bucket.name}"
                ) as file_obj:
                    blob.upload_from_file(file_obj, size=total_bytes)
        else:
            print(f"{destination} already uploaded")

        print("Done uploading")
        gcs_uri = f"gs://{Global_Config.BUCKET_NAME}/{destination}"
        return gcs_uri

    def serialize_operation(self, future, name):
        now = datetime.now().strftime("%Y-%m-%d %H;%M;%S")
        # if isinstance(future, _video_intelligence.AnnotateVideoResponse):
        #     operation = future._pb
        # else:
        #     operation = future.operation
        operation_json = json_format.MessageToJson(future.operation)
        # Convert operation protobuf message to JSON-formatted string

        output_path = Path(f"{self.response_output_folder}/{name}_{now}.operation").resolve()
        output_path.parent.mkdir(exist_ok=True,parents=True)
        json.dump(operation_json, Path(f"{self.response_output_folder}/{name}_{now}.operation").open("w"))
        return operation_json

    def serialize_response(self, response, name):
        now = datetime.now().strftime("%Y-%m-%d %H;%M;%S")
        response_path = Path(f"{self.response_output_folder}/{name}_{now}.response")
        try:
            operation_json = json_format.MessageToJson(response)
        except: # video_intelligence.AnnotateVideoResponse
            response = response._pb
            operation_json = json_format.MessageToJson(response)
        badjuju = """"@type": "type.googleapis.com/google.cloud.videointelligence.v1.AnnotateVideoResponse","""
        if badjuju in operation_json:
            operation_json = operation_json.replace(badjuju, "")
            json.dump(operation_json, response_path.open("w"))
            response = self.load_response(response_path)
        else:
            json.dump(operation_json, response_path.open("w"))
        return response

    def restore_operation(self, json_path):
        """ Restores a long-running operation from a JSON file.

        Args:
            json_path: Path to the .operation JSON file.

        Returns:
            google.api_core.operation.Operation: The restored operation future.
        """
        # Convert JSON-formatted string to proto message
        operation_json = json.load(Path(json_path).open())
        operation = json_format.Parse(operation_json, operations_pb2.Operation())

        # load operation from backing store

        """
                operation,
        refresh,
        cancel,
        result_type,
        """

        if self.api=="speech":
            future = from_gapic(
                operation=operation,
                operations_client=self.client.transport._operations_client,
                result_type=cloud_speech_pb2.LongRunningRecognizeResponse,
                metadata_type=cloud_speech_pb2.LongRunningRecognizeMetadata
            )
        else:
            future = from_gapic(
                operation=operation,
                operations_client=self.client.transport.operations_client,
                result_type=_video_intelligence1.AnnotateVideoResponse,
                metadata_type=_video_intelligence1.AnnotateVideoProgress
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
            operation = self.restore_operation(Path(f"{self.response_output_folder}/{name}.operation"))
        done = False

        i = 0
        while not done:
            i += 1
            print("Waiting for response...")
            try:
                response = operation.result(timeout=60)
                if response is None:
                    if hasattr(operation, "operation"):
                        response = operation.operation.response
                        done = True
                        # NOT WORKING YET - THIS HAPPENS WHEN LOADING AN OPERATION
                else:
                    done = True

            except Exception as e:
                if i > 30 and i % 10 == 0:
                    print(e)
                print("TRYING SOMETHING ELSE")
                try:
                    if hasattr(operation.metadata, "progress_percent"):
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

    def submit_operation(self, storage_uri, name=None):
        """Submit a transcription operation without polling. Returns (operation, name).
        
        Use with poll_all_operations() to process multiple segments concurrently.
        """
        if name is None:
            name = Path(storage_uri).stem
        
        if self.api == "speech":
            operation = self.create_speech_operation(storage_uri=storage_uri)
        elif self.api == "video":
            operation = self.create_video_speech_operation(storage_uri=storage_uri)
        else:
            raise Exception(f"Unknown API: {self.api}")
        
        self.serialize_operation(operation, name=name)
        return operation, name

    def poll_all_operations(self, operations):
        """Poll multiple operations concurrently until all complete.
        
        Args:
            operations: List of (operation, name) tuples from submit_operation.
            
        Returns:
            List of (response, name) tuples in the same order.
        """
        pending = {i: (op, name) for i, (op, name) in enumerate(operations)}
        results = [None] * len(operations)
        
        while pending:
            still_pending = {}
            for i, (operation, name) in pending.items():
                try:
                    response = operation.result(timeout=5)
                    if response is not None:
                        try:
                            response = self.serialize_response(response, name=name)
                        except:
                            traceback.print_exc()
                        results[i] = (response, name)
                        print(f"  ✓ Segment '{name}' transcription complete.")
                        continue
                except Exception:
                    # Still in progress — check metadata for progress
                    try:
                        if hasattr(operation.metadata, "progress_percent"):
                            pct = operation.metadata.progress_percent
                        else:
                            pct = operation.metadata.annotation_progress._pb[0].progress_percent
                        print(f"  [{name}] {pct}%")
                    except:
                        print(f"  [{name}] waiting...")
                still_pending[i] = (operation, name)
            
            pending = still_pending
            if pending:
                sleep(10)
        
        return results

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
        path.mkdir(exist_ok=True, parents=True)
        
        # New workflow: Words -> CSV -> Mute List
        words = self.get_words_from_response(response)
        
        # Save words to CSV for manual editing
        csv_path = self.response_output_folder / f"{name}_words.csv"
        self.save_words_to_csv(words, csv_path)
        print(f"Exported words to {csv_path}")

        mute_list, transcript, _ = self.create_mute_list_from_words(words)
        
        pickle.dump({"mute_list": mute_list, "transcript": transcript},
                    (path / f"{name}.pickle").open("wb"))
        return mute_list, transcript

    def get_words_from_response(self, response):
        def convert_to_seconds(word_time):
            if hasattr(word_time, "nanos"):
                start = word_time.seconds + word_time.nanos * 10 ** -9
            elif hasattr(word_time, "microseconds"):
                start = word_time.seconds+word_time.microseconds*1e-6
            else:
                # v1 types might be different
                start = word_time.seconds + word_time.nanos * 1e-9
            return start

        words = []
        if "Annotate" in str(type(response)):
             # Handle possible different structures if using v1 vs v1p3beta1
             if hasattr(response, "annotation_results"):
                results = [x for x in response.annotation_results[0].speech_transcriptions]
             else:
                 # v1 structure might be in payload or similar? 
                 # Actually v1 `AnnotateVideoResponse` has `annotation_results` too.
                 results = [x for x in response.annotation_results[0].speech_transcriptions]
        else:
            results = response.results

        strip_punctuation = re.compile('[^-a-zA-Z \']+')
        
        for result in results:
            for i, alternative in enumerate(result.alternatives):
                # We only take the first alternative usually
                if i > 0: continue 
                
                for word_info in alternative.words:
                     start = convert_to_seconds(word_info.start_time)
                     end = convert_to_seconds(word_info.end_time)
                     word_text = getattr(word_info, "word", "")
                     confidence = getattr(word_info, "confidence", 0.0)
                     
                     words.append({
                         "word": word_text,
                         "start": start,
                         "end": end,
                         "confidence": confidence
                     })
        return words

    def save_words_to_csv(self, words, path):
        import csv
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=["start", "end", "word", "confidence"])
            writer.writeheader()
            for w in words:
                writer.writerow(w)

    def load_words_from_csv(self, path):
        import csv
        words = []
        with open(path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
             words.append({
                 "word": row["word"],
                 "start": float(row["start"]),
                 "end": float(row["end"]),
                 "confidence": float(row.get("confidence", 0.0))
             })
        return words

    def create_mute_list_from_words(self, words, subtitle_confirmed_words=None):
        """Create mute list from transcribed words.
        
        Args:
            words: List of word dicts with 'word', 'start', 'end' keys.
            subtitle_confirmed_words: Optional set of words that appear in subtitles.
                If a word is in subtitle_exceptions AND in this set, it won't be muted.
        """
        mute_list = []
        mute_details = []  # (start, end, censored_word) for human-readable report
        transcript = []
        cleaned_transcript = []
        
        strip_punctuation = re.compile('[^-a-zA-Z \']+')
        
        previous_word = ""
        previous_start_time = 0.0
        
        phrase_buffer = []
        subtitle_confirmed_words = subtitle_confirmed_words or set()

        for i, word_obj in enumerate(words):
            word_text = word_obj["word"]
            start = word_obj["start"]
            end = word_obj["end"]
            
            phrase_buffer.append(word_text)
            
            _word = strip_punctuation.sub("", word_text).lower()
            compound_phrase = f"{previous_word} {_word}".strip()
            
            # Check if word is in subtitle exceptions and confirmed by subtitles
            is_exception = _word in self.subtitle_exceptions and _word in subtitle_confirmed_words
            
            if compound_phrase in self.swears and previous_start_time:
                # Mute the compound phrase (e.g., "god damn")
                # Check if compound is exceptioned
                compound_is_exception = (
                    compound_phrase in self.subtitle_exceptions and 
                    compound_phrase in subtitle_confirmed_words
                )
                if not compound_is_exception:
                    mute_list.append((previous_start_time, end))
                    mute_details.append((previous_start_time, end, compound_phrase[0] + '*' * (len(compound_phrase) - 1)))
            elif _word in self.swears:
                if is_exception:
                    # Word is allowed because it's in subtitles
                    cleaned_transcript.append(word_text)
                else:
                    censored = word_text[0] + "*"*(len(_word)-1)
                    mute_list.append((start, end))
                    mute_details.append((start, end, censored))
                    cleaned_transcript.append(censored)
            else:
                cleaned_transcript.append(word_text)

            previous_word = _word
            previous_start_time = start
            
        transcript = [" ".join(phrase_buffer)]
        print(" ".join(cleaned_transcript))
        return mute_list, transcript, mute_details

    def create_mute_list_from_response(self, response):
        # Legacy method kept for compatibility if needed, but refactored to use new pipeline
        words = self.get_words_from_response(response)
        return self.create_mute_list_from_words(words)

    def resume_operation(self, name):
        response = self.get_response(name=name)
        mute_list, transcript = self.create_mute_list_from_response(response)
        return mute_list

    def load_response(self, json_path):
        response_json = json.load(Path(json_path).open("r"))
        
        # Auto-detect type based on JSON content
        # Video Intelligence has 'annotationResults'
        # Speech has 'results' (or 'alternatives' nested strictly)
        
        # Note: json_format.Parse needs the correct target message.
        
        if "annotationResults" in response_json:
             response = json_format.Parse(response_json, _video_intelligence.AnnotateVideoResponse()._pb)
        else:
             response = json_format.Parse(response_json, cloud_speech_pb2.LongRunningRecognizeResponse())

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