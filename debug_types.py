from google.cloud.videointelligence_v1p3beta1.types import video_intelligence as _video_intelligence
from google.cloud.videointelligence_v1.types import video_intelligence as _video_intelligence1

print("v1p3beta1 types:")
print(dir(_video_intelligence))

print("\nv1 types:")
print(dir(_video_intelligence1))

try:
    print(f"\nAnnotateVideoProgress in v1p3beta1: {_video_intelligence.AnnotateVideoProgress}")
except AttributeError:
    print("AnnotateVideoProgress not found in v1p3beta1")

try:
    print(f"AnnotateVideoProgress in v1: {_video_intelligence1.AnnotateVideoProgress}")
except AttributeError:
    print("AnnotateVideoProgress not found in v1")
