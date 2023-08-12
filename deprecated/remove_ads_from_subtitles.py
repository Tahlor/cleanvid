import os
import re

# Define the patterns to remove using regular expressions
patterns_to_remove = [
    "opensubtitles",  # remove "opensubtitles"
    "Advertisement",  # remove "Advertisement"
    "^.*keyword.*\n"
    # Add your own patterns here using the same format
]

# Define the directory where the subtitle files are stored
directory = "/path/to/subtitles"

# Loop through all files in the directory
for filename in os.listdir(directory):
    if filename.endswith(".srt"):
        # Read the contents of the subtitle file
        with open(os.path.join(directory, filename), "r") as file:
            contents = file.read()

        # Remove the specified patterns using regular expressions
        for pattern in patterns_to_remove:
            contents = re.sub(pattern, "", contents, flags=re.IGNORECASE)

        # Save the cleaned subtitles to the same file
        with open(os.path.join(directory, filename), "w") as file:
            file.write(contents)
