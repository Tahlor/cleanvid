import traceback
from mutagen.mp4 import MP4
from pathlib import Path
import re
import os

TESTING = False
CONFIRM_TAG_CHANGE = False
CONFIRM_RENAME = False

class Cleaner:

    def __init__(self):
        self.all_words, self.tag_words = self.get_wordlists()
        self.all_words_re, self.tag_words_re = self.create_regex()
        self.strip_whitespace = re.compile(" +")
        self.strip_duplicate_periods = re.compile("\.+")

    def create_regex(self):
        all_words_re, tag_words_re = [], []
        for word in self.all_words:
            pattern = re.compile(word.strip(), re.IGNORECASE)
            all_words_re.append(pattern)
            if word in self.tag_words:
                tag_words_re.append(pattern)
        return all_words_re, tag_words_re

    def get_wordlists(self):
        all_words = Path("file_blacklist").open().readlines() # bloc
        tag_words = Path("tag_blacklist").open().readlines() # don't block in meta data
        all_words = list(set(all_words+tag_words))
        all_words.sort(key=lambda s: -len(s))
        tag_words.sort(key=lambda s: -len(s))
        return all_words, tag_words

    def clean_metadata(self, file_path):
        mp4 = MP4(file_path)
        tag_changed = 0

        if mp4.tags is None:
            return

        for tag_key in mp4.tags:
            original_tag = mp4.tags[tag_key]
            is_iter = True
            if not is_iterable(original_tag):
                original_tag = [original_tag]
                is_iter = False
            output_tag = original_tag.copy()
            for i, tag in enumerate(original_tag):
                ot = tag ; is_bytes = 0;
                if not tag:
                    continue
                try:
                    tag = tag.decode()
                    is_bytes = 1
                    continue # don't mess with bytes stuff
                except (UnicodeDecodeError, AttributeError):
                    pass
                if not isinstance(tag, str):
                    continue

                for pattern in self.tag_words_re:
                    #print(f"Tag: {tag}")
                    tag = pattern.sub("", tag)
                tag = self.general_cleaning(tag, periods=False)

                if tag != ot:
                    tag_changed = 1
                if is_bytes:
                    tag = tag.encode()
                output_tag[i] = tag
            if not is_iter:
                output_tag = output_tag[0]
            mp4.tags[tag_key] = output_tag
            if original_tag != output_tag:
                print(f"Tag {original_tag} -> {output_tag}")
        #mp4.clear()
        #mp4.clear()
        if tag_changed:
            save = input("Save? Y/n ") if CONFIRM_TAG_CHANGE else "y"
            if save.lower() == "y" and not TESTING:
                mp4.save()

    def has_n_chars(self, word, n=2, char="."):
        count = 0
        for letter in word:
            if letter == char:
                count+=1
                if count >= n:
                    return True
        return False

    def general_cleaning(self, name, periods=True):
        # remove periods if there are more than 2
        if periods and self.has_n_chars(name):
            name = name.replace(".", " ")

        # underscores for spaces
        if self.has_n_chars(name):
            name = name.replace("_", " ")

        # empty parens
        name = name.replace("[]","")
        name = name.replace("()", "")

        ## Finally
        # remove double spaces, leading and trailing spaces
        name = self.strip_whitespace.sub(" ", name).strip(" *([_-~@#$%^&,/\\`")
        name = self.strip_duplicate_periods.sub(".", name)
        return name


    def propose_new_name(self, old_name):
        # remove words
        suffix = Path(old_name).suffix
        old_name = Path(old_name).stem
        for pattern in self.all_words_re:
            old_name = pattern.sub("", old_name)
        old_name = self.general_cleaning(old_name)
        return Path(old_name+suffix)

    def clean_file_name(self, old_name):
        new_name = self.propose_new_name(old_name)
        if new_name == Path(old_name):
            return old_name
        if CONFIRM_RENAME:
            user_entry = input(f"File name change: {old_name} :::: {new_name}? Y/n ")
            if user_entry.lower()=="y":
                pass
            elif user_entry.lower()=="n":
                return old_name
            else:
                user_entry2 = f"Use {user_entry}? Y/n "
                if user_entry2.lower() == "y":
                    new_name = user_entry
                else:
                    return old_name
        else:
            print(f"File name change: {old_name} :::: {new_name}")
        return new_name

    def clean(self, path="Q:\Media\Videos\Movies\Kids"):
        for ext in "mp4", ".avi", ".mkv", "":
            for f in Path(path).rglob(f"*{ext}"):
                if ext == "" and not f.is_dir():
                    continue
                try:
                    # Clean meta data
                    if f.suffix==".mp4":
                        self.clean_metadata(f)

                    # Clean file name
                    new_name = self.clean_file_name(f.name)
                    if not TESTING:
                        f.rename(f.parent / new_name)
                except Exception as e:
                    print(e)
                    traceback.print_exc()


def is_iterable(object, string_is_iterable=True):
    """Returns whether object is an iterable. Strings are considered iterables by default.

    Args:
        object (?): An object of unknown type
        string_is_iterable (bool): True (default) means strings will be treated as iterables
    Returns:
        bool: Whether object is an iterable

    """

    if not string_is_iterable and type(object) == type(""):
        return False
    try:
        iter(object)
    except TypeError as te:
        return False
    return True


if __name__=='__main__':
    Cleaner().clean("Q:\Media\Videos\Movies\Kids\Winnie the Pooh, A Very Merry Pooh Year (2002) [G]")