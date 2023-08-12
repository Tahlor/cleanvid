import hashlib
import os
from pathlib import Path
import re

def get_hash_of_file(file_path):
    BUF_SIZE = 65536  # read file in 64kb chunks
    sha256 = hashlib.sha256()

    with open(file_path, 'rb') as f:
        while True:
            data = f.read(BUF_SIZE)
            if not data:
                break
            sha256.update(data)
    return sha256.hexdigest()

def remove_duplicate_files(root_dir):
    hash_dict = {}
    for path in Path(root_dir).rglob("*.srt"):
        file_hash = get_hash_of_file(path)
        if file_hash not in hash_dict:
            hash_dict[file_hash] = path
        else:
            original_file = hash_dict[file_hash]
            if (re.search(r'\d.en.srt$', str(original_file)) and re.search(r'\d.en.srt$', str(path)) and
               int(re.search(r'(\d).en.srt$', str(original_file)).group(1)) > int(re.search(r'(\d).en.srt$', str(path)).group(1))) or \
               (not re.search(r'\d.en.srt$', str(original_file)) and re.search(r'\d.en.srt$', str(path))):
                os.remove(original_file)
                hash_dict[file_hash] = path
            else:
                print(f"Removing {path}")
                os.remove(path)
                backup = (path.parent / f"{path.name}.bak")
                if backup.exists():
                    os.remove(backup)

def remove_baks_with_no_main(root_dir):
    for path in Path(root_dir).rglob("*.srt.bak"):
        if not (path.parent / path.name.replace(".bak", "")).exists():
            print(f"Removing {path}")
            os.remove(path)


if __name__ == "__main__":
    root = "J:\Media\Videos"
    #root = "J:\Media\Videos\Movies\Church\Home Teachers, The (2004) [Unknown] [PG]"
    remove_baks_with_no_main(root)
    remove_duplicate_files(root)
