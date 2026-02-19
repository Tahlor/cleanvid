import re
from pathlib import Path
import os
import fileinput
import re
import sys


# Match any part of this string to delete the section
string_list = ["OpenSubtitles.org", "Support us","Subtitles by","Advertise your product", "Corrected by", "OpenSubtitles", "www."]
matched = re.compile(rf"({'|'.join(string_list)})").search

def _test():
    test = """
    Advertise your product or brand here
    contact www.OpenSubtitles.org today
    
    2
    00:00:43,130 --> 00:00:48,130
    Subtitles by explosiveskull
    www.OpenSubtitles.org
    Support us
    Support us
    Support us
    1570
    01:42:34,350 --> 01:42:39,350
    Subtitles by explosiveskull
    www.OpenSubtitles.org
    
    1570
    01:42:40,305 --> 01:42:46,326
    Support us and become VIP member
    to remove all ads from www.OpenSubtitles.org
    
    """

    lines =  test.split("\n")
    for line in lines:
        if matched(line):
            print(line)

def strip_ads(path, redo=False):
    dropped = []
    if path.with_suffix(path.suffix + ".bak").exists() and not redo:
        print("Skipping", path)
        return
    with fileinput.FileInput(path, inplace=1, backup='.bak') as file:
        for line in file:
            if not matched(line):  # save lines that do not match
                print(line, end='')  # this goes to filename due to inplace=1
            else:
                dropped.append(line)
    print(dropped, path)


if __name__=='__main__':
    #root = input("Subtitle root directory: ") # "%LOCALAPPDATA%\Plex Media Server\Media\localhost\0"
    #root = r"%LOCALAPPDATA%\Plex Media Server\Media\localhost\0"
    #root = r"C:\Users\Taylor\AppData\Local\Plex Media Server\Media"
    root = "J:\Media\Videos"
    print(Path(root).resolve())

    for path in Path(root).rglob("*.srt"):
        try:
            strip_ads(path)
        except:
            pass
