import re
from pathlib import Path
import os
import fileinput
import re
import sys


string_list = ["www.OpenSubtitles.org", "Support us","Subtitles by","Advertise your product"]
matched = re.compile(rf"({'|'.join(string_list)})").search


def test():
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

def strip_ads(path):
    with fileinput.FileInput(path, inplace=1, backup='.bak') as file:
        for line in file:
            if not matched(line):  # save lines that do not match
                print(line, end='')  # this goes to filename due to inplace=1


root = input("Subtitle root directory: ")
for path in Path(root).rglob("*.srt"):
    strip_ads(path)