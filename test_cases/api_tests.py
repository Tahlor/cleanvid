import pytest
import utils
import decorator
from pathlib import Path
import os
from google_api import google_speech_api
from utils import process_config

def test_load_response():
    """ Load a saved response and parse for muting

    Returns:

    """
    # Load old response
    config = process_config()
    ga = google_speech_api(**config)
    response = ga.load_response(config.response_path)
    mute_list, transcript = ga.create_mute_list_from_response(response)
    print(response.results)
    print(mute_list)

def test_resume_op():
    """ Download from a previously started operation

    Returns:

    """
    config = process_config()
    ga = google_speech_api(**config)
    ga.resume_operation(config.load_operation_path)

def test_full():
    """ Take a config, process video, upload, process in Cloud, download response, process result

    Returns:

    """
    config = process_config()
    ga = google_speech_api(**config)
    mute_list, transcript = ga.process_speech(config.uri)
