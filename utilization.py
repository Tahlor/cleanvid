"""
Utilization Tracking for CleanVid Pipeline

Tracks monthly usage of Google Speech-to-Text API credits/minutes.
Usage is stored persistently in a pickle file and updated when requests are submitted.
"""

import pickle
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
import Global_Config


def get_current_month() -> str:
    """Get current month as 'YYYY Month' string."""
    today = datetime.today()
    return datetime(today.year, today.month, 1).strftime("%Y %B")


def load_utilization() -> Dict:
    """Load utilization data from file."""
    util_file = Global_Config.UTILIZATION_FILE
    
    try:
        with util_file.open("rb") as f:
            data = pickle.load(f)
    except (FileNotFoundError, EOFError):
        print(f"Utilization file not found, creating new tracker.")
        data = {}
    except Exception as e:
        print(f"Error loading utilization: {e}")
        data = {}
    
    # Ensure current month exists
    month = get_current_month()
    if month not in data:
        data[month] = 0
    if f"{month} dict" not in data:
        data[f"{month} dict"] = {}
        
    return data


def save_utilization(data: Dict) -> None:
    """Save utilization data to file."""
    util_file = Global_Config.UTILIZATION_FILE
    util_file.parent.mkdir(parents=True, exist_ok=True)
    
    with util_file.open("wb") as f:
        pickle.dump(data, f)


def get_monthly_usage() -> float:
    """Get current month's usage in minutes."""
    data = load_utilization()
    month = get_current_month()
    return data.get(month, 0) / 60  # Convert seconds to minutes


def get_monthly_limit() -> float:
    """Get configured monthly limit in minutes."""
    return Global_Config.MAX_MONTHLY_MINUTES


def get_remaining_credits() -> float:
    """Get remaining credits in minutes."""
    return get_monthly_limit() - get_monthly_usage()


def is_over_limit() -> bool:
    """Check if we've exceeded the monthly limit."""
    return get_monthly_usage() >= get_monthly_limit()


def add_usage(video_name: str, duration_seconds: float) -> None:
    """
    Add usage for a transcription request.
    Call this WHEN the request is successfully submitted, not when it completes.
    """
    data = load_utilization()
    month = get_current_month()
    
    data[month] = data.get(month, 0) + duration_seconds
    data[f"{month} dict"][video_name] = duration_seconds
    
    save_utilization(data)
    
    usage_min = data[month] / 60
    print(f"📊 Added {duration_seconds/60:.1f} min. Monthly total: {usage_min:.1f} / {get_monthly_limit()} min")


def get_usage_summary() -> str:
    """Get a human-readable usage summary."""
    data = load_utilization()
    month = get_current_month()
    
    used = data.get(month, 0) / 60
    limit = get_monthly_limit()
    remaining = limit - used
    pct = (used / limit * 100) if limit > 0 else 0
    
    return f"Usage for {month}: {used:.1f} / {limit} min ({pct:.1f}% used, {remaining:.1f} min remaining)"


if __name__ == "__main__":
    # Quick test / status check
    print(get_usage_summary())
    
    data = load_utilization()
    month = get_current_month()
    
    if f"{month} dict" in data and data[f"{month} dict"]:
        print("\nVideos processed this month:")
        for name, secs in data[f"{month} dict"].items():
            print(f"  - {name}: {secs/60:.1f} min")
