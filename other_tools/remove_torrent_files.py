import argparse
import pathlib
import sys

def delete_files(source_dir: str, delete_set: set):
    source_path = pathlib.Path(source_dir)
    for file_path in source_path.rglob('*'):
        print(file_path)
        if file_path.name in delete_set:
            file_path.unlink()
            print(f"Deleted: {file_path}")

def parse_args(args=None):
    parser = argparse.ArgumentParser(description="Recursively delete specific files.")
    parser.add_argument("--source_dir", type=str, help="Directory to search for files.")
    parser.add_argument("--delete_set", type=str, nargs='+', help="Set of filenames to delete.")
    return parser.parse_args(args)

if __name__ == "__main__":

    if len(sys.argv) > 1:
        args = parse_args()
        source_dir = args.source_dir
        delete_set = set(args.delete_set)
    else:
        source_dir = "J:\\Media\\Videos"
        delete_set = {
            "WWW.YIFY-TORRENTS.COM.jpg",
            "RARBG_DO_NOT_MIRROR.exe",
            "RARBG.txt",
        }
    #print(delete_set)
    delete_files(source_dir, delete_set)
