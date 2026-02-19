from google_api import google_speech_api
from easydict import EasyDict as edict
import os
from pathlib import Path

# Mock config
config = edict({
    "api_response_root": Path("d:/Github/cleanvid/data/google_api")
})

# Initialize API
# Need credential path
credential_path = r"d:\Github\cleanvid\credentials\Speech to Text-0bc76bdcf21a.json"


api = google_speech_api(credential_path=credential_path, config=config, api="video")

# Verify restore_operation
try:
    op_path = r"d:\Github\cleanvid\data\google_api\The.Right.Stuff.1983.1080p.BluRay.x265-RARBG_2026-02-06 19;28;38.operation"
    print(f"Restoring {op_path}")
    operation = api.restore_operation(op_path)
    print("Operation restored.")
    
    # Force a refresh to get the latest state from server
    try:
        # Checking done() triggers a refresh
        is_done = operation.done()
        print(f"Operation done: {is_done}")
        
        if is_done:
            # Inspect the raw proto response type URL
            if hasattr(operation._operation, "response"):
                response_any = operation._operation.response
                print(f"Response Any type_url: {response_any.type_url}")
            else:
                print("Operation is done but has no response field set (might be error)")
                
            if hasattr(operation._operation, "error"):
                 print(f"Operation error: {operation._operation.error}")

            # Now try result() to see if it crashes
            res = operation.result(timeout=10)
            print("Result retrieved successfully")
    except Exception as e:
        print(f"Error during refresh or result: {e}")
        # If we have the updated operation, check response type url again
        if hasattr(operation, "_operation") and hasattr(operation._operation, "response"):
             print(f"Response Any type_url: {operation._operation.response.type_url}")
        
    print("Done")
except Exception as e:
    print(f"Failed: {e}")
    import traceback
    traceback.print_exc()
