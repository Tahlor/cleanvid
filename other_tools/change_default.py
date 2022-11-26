import delegator
from pathlib import Path

def change_default_track(input, output=None, track=0, overwrite=False):
    input = Path(input)
    if output is None:
        output = input.parent / (input.stem + "_fixed" + input.suffix)
    if output.exists() and not overwrite:
        print("Already exists")
        return

    command = f"""
    ffmpeg -i "{input}" -c copy -map 0 
    -metadata:s:a:0 title="Clean" 
    -metadata:s:a:0 language=eng 
    -metadata:s:a:1 title="Original" 
    -disposition:a:{track} default  "{output}"
    """.replace("\n","")
    ffmpegResult = delegator.run(command,
                                 block=True)
    return ffmpegResult

if __name__=='__main__':

    folder = "J:\Media\Videos\Misc Videos\msc"
    folders = [r"J:\Media\Videos\Movies\Unorganized\Jurassic Park (1993) [1080p] [PG-13]"]

    for folder in folders:
        video_extensions = ["*.mp4","*.avi", "*.mkv", "*.m4v"]
        for ext in video_extensions:
            for movie in Path(str(folder).lower()).rglob(ext.replace("*", "*_clean")):
                print(f"{movie.stem} - {movie}")
                result = change_default_track(movie)
                print(result)