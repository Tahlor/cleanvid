from mutagen.mp4 import MP4
from pathlib import Path
import re
import os

class Cleaner:

    def __init__(self, path, ):


        self.all_words, self.file_words = self.get_wordlists()

    def get_wordlists(self):
        all_words = Path("blacklist").open().read() # bloc
        file_words = Path("file_only_blacklist").open().read() # don't block in meta data
        all_words = set(all_words+file_words)
        return all_words, file_words

    def clean_metadata(self, file_path):
        movie_tags = MP4(file_path)
        #movie_tags.clear()
        #movie_tags.save()

    def propose_new_name(self, old_name):
        # remove words


        # remove periods if there are more than 2

        ## Finally
        # remove double spaces, leading and trailing spaces
        pass

    def clean_file_name(self, old_name):
        new_name = self.propose_new_name(old_name)
        input(f"{old_name} {new_name}")


    def clean(self, path="Q:\Media\Videos\Movies\Kids"):
        for ext in "mp4", ".avi", ".mkv", "":
            for f in Path(path).rglob(f"*{ext}"):
                if ext == "" and not f.is_dir():
                    continue
                # Clean meta data
                self.clean_metadata(f)

                # Clean file name
                self.clean_file_name(f.stem)
