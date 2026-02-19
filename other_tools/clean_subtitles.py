import shutil
import re
from pathlib import Path
import os
import fileinput
import sys
import logging

PARENT = Path(os.path.dirname(os.path.realpath(__file__)))
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)
fh = logging.FileHandler(PARENT / "logs"/ 'clean_subtitles.log')
fh.setLevel(logging.DEBUG)
logger.addHandler(fh)

SWEARS = PARENT.parent / "all_swears.txt"

# Advertisements to remove
string_list = ['\.SE', '\.ONLINE', '\.ONE', '\.DE', '\.ES', '\.BE', '\.FM', '\.MS', 'Advertise your product',
               '\.HOST', 'OpenSubtitles', '\.TF', '\.GS', '\.CC', '\.DK', '\.AG', '\.LIVE', '\.LI',
               'Support us', '\.STORE', '\.BIZ', '\.MX', '\.AE', '\.SH', '\.WS', '\.NEWS', '\.LT', '\.LIFE',
               '\.VG', '\.VC', '\.YT', '\.RE', '\.CZ', '\.NZ', '\.CH', '\.CA', '\.IN', '\.IM', '\.EMAIL',
               '\.SG', '\.SC', '\.TK', '\.PE', '\.MU', '\.NET', '\.IO', '\.PRO', '\.NF', '\.LA', '\.TO',
               '\.MOBI', 'subtitles', '\.DESIGN', '\.TV', '\.COM', '\.TM', '\.RO', '\.TL', '\.PH', '\.ORG',
               '\.TECH', '\.JP', '\.RU', '\.NU', '\.SITE', 'HIGH QUALITY', '\.AT', '\.TC', '\.MN', '\.FR',
               '\.BZ', '\.VN', '\.EU', '\.LOVE', '\.FUN', '\.AM', '\.SPACE', '\.ME', '\.NL', '\.TW', 'YIFY',
               '\.CLOUD', '\.APP', '\.PL', '\.GURU', '\.BLOG', '\.AC', '\.HK', '\.SHOP', '\.INFO', '\.IT',
               '\.CO', 'www\.YTS', '\.US', '\.NO', '\.SK', 'Subtitles by', '\.LU', '\.IS', 'Corrected by',
               'LIVE TV']

matched_ad = re.compile(rf"({'|'.join(string_list)})", re.IGNORECASE).search

# Load profanity list from file
with open(SWEARS, 'r') as f:
    profanity_list = [line.strip() for line in f]

# Compile case-insensitive regex for profanity
profanity_regex = re.compile(rf"\b({'|'.join(profanity_list)})\b", re.IGNORECASE)

def censor_profanity(line):
    line = profanity_regex.sub(lambda m: '*'*len(m.group()), line)
    return line

def strip_ads_and_profanity(path, redo=False):
    if path.with_suffix(path.suffix + ".bak").exists() and not redo:
        logger.info(f"Skipping: {path}")
        return
    else:
        logger.info(f"Processing: {path}")

    if redo:
        logger.info(f"Redoing: {path}")
        backup_file = path.with_suffix(path.suffix + ".bak")
        if backup_file.exists():
            shutil.copyfile(backup_file, path)

    with fileinput.FileInput(path, inplace=1, backup='.bak') as file:
        for i, line in enumerate(file):
            if i == 0:  # Insert a comment on the first line
                print("""0
00:00:00,000 --> 00:00:00,000
This file has been modified to remove ads and profanity\n""")
            if not matched_ad(line):  # save lines that do not match
                new_line = censor_profanity(line)  # censor any profanity in the line
                print(new_line, end='')  # this goes to filename due to inplace=1
            else:
                print(end='')

def argparse(args=None):
    import argparse
    parser = argparse.ArgumentParser(description='Strip ads and profanity from subtitle files')
    parser.add_argument('--root', default="J:\Media\Videos", type=str, help='Root directory to search for subtitle files')
    parser.add_argument('--redo', action='store_true', help='Redo files that have already been processed')
    if args:
        if isinstance(args, str):
            import shlex
            args = shlex.split(args)
        return parser.parse_args(args)
    return parser.parse_args()

if __name__=='__main__':
    root = "J:\Media\Videos"
    #root = "J:\Media\Videos\TV\Parents\Hijack"
    print(Path(root).resolve())
    args = argparse()
    #args.redo = True
    for path in Path(root).rglob("*.srt"):
        try:
            strip_ads_and_profanity(path, redo=args.redo)
        except Exception as e:
            logger.info(f"Error processing {path}: {e}")
            continue
    logger.info("Done!")
