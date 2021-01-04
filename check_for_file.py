from google.cloud import storage
import re
import os

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"./credentials/Speech to Text-0bc76bdcf21a.json"

storage_client = storage.Client()
try:
    bucket = storage_client.create_bucket("remove_profanity_from_movie_project")
except:
    pass

# Browse Bucket: https://console.cloud.google.com/storage/browser/remove_profanity_from_movie_project?forceOnBucketsSortingFiltering=false&project=speech-to-text-1590881833772
bucket = storage_client.get_bucket("remove_profanity_from_movie_project")

def check(destination):
    destination = re.sub("[#\[\]*?]", "_", destination)
    exists = storage.Blob(bucket=bucket, name=destination).exists(storage_client)
    print(destination)
    print("Exists", exists)

def list(bucket_name):
    blobs = storage_client.list_blobs(bucket_name)

    for blob in blobs:
        print(blob.name)

destination = "Hill_Billy_Elegy/E.mp4"
check(destination)