from pathlib import Path

# Google Cloud Storage Configuration
BUCKET_NAME = "remove_profanity_from_movie_project"
GCS_CREDENTIALS_PATH = Path(r"./credentials/Speech to Text-0bc76bdcf21a.json")

# File Retention Policy (in hours)
RETENTION_HOURS_SUCCESS = 0  # Delete immediately after successful processing
RETENTION_HOURS_FAILURE = 48 # Keep for 48 hours if processing failed or was interrupted

# Utilization / Credit Tracking
MAX_MONTHLY_MINUTES = 1000  # Maximum minutes allowed per month (configurable)
UTILIZATION_FILE = Path("./personal/utilization")  # Pickle file for tracking

# Default Batch File
DEFAULT_BATCH_FILE = Path("./personal/BATCH.txt")

# Other Constants
# Add other global constants here as needed
