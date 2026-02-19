from google.cloud import storage
from datetime import datetime, timedelta, timezone
import os
import sys

# Add parent directory to sys.path to allow importing Global_Config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import Global_Config

# Set credentials if not already set (relying on environment or default)
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(Global_Config.GCS_CREDENTIALS_PATH)


def cleanup_bucket(bucket_name=Global_Config.BUCKET_NAME, hours=Global_Config.RETENTION_HOURS_FAILURE, dry_run=False):
    """
    Deletes blobs from the bucket that are older than 'hours'.
    """
    storage_client = storage.Client()
    try:
        bucket = storage_client.get_bucket(bucket_name)
    except Exception as e:
        print(f"Error accessing bucket {bucket_name}: {e}")
        return

    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    print(f"Checking for files older than {hours} hours (created before {cutoff_time})...")

    blobs = list(storage_client.list_blobs(bucket_name))
    
    for blob in blobs:
        if blob.time_created < cutoff_time:
            print(f"Deleting {blob.name} (Created: {blob.time_created})")
            if not dry_run:
                try:
                    blob.delete()
                    print(f"Deleted {blob.name}")
                except Exception as e:
                    print(f"Failed to delete {blob.name}: {e}")
        else:
            # print(f"Skipping {blob.name} (Created: {blob.time_created})")
            pass

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Cleanup old files from GCS bucket.")
    parser.add_argument("--hours", type=int, default=Global_Config.RETENTION_HOURS_FAILURE, help="Delete files older than this many hours.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be deleted without actually deleting.")
    
    args = parser.parse_args()
    
    cleanup_bucket(hours=args.hours, dry_run=args.dry_run)
