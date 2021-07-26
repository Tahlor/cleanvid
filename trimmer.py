"""
Not working, seems to require re-encoding

ffmpeg -i input.mp4 -ss 00:02:00 -t 00:07:28 part1.mp4
ffmpeg -i input.mp4 -ss 00:10:50 -t 00:51:30 part2.mp4
ffmpeg -i input.mp4 -ss 01:19:00 -t 00:08:05 part3.mp4

inputs.txt
file 'part1.mp4'
file 'part2.mp4'
file 'part3.mp4'


ffmpeg -f concat -i inputs.txt -c copy output.mp4

"""

import datetime
from pathlib import Path
import os
import subprocess
import shutil
input_file = "J:\Media\Videos\Misc Videos\msc\The Matrix Reloaded (2003) [1080p]\The.Matrix.Reloaded.2003.1080p.BrRip.x264.YIFY_clean.mp4"
#input_file = "J:\Media\Videos\Misc Videos\msc\The Matrix Reloaded (2003) [1080p]\The.Matrix.Reloaded.2003.1080p.BrRip.x264.YIFY.mp4"
#input_file = "J:\Media\Videos\Misc Videos\msc\Goodfellas\Goodfellas R (1990).avi"

list_of_cuts=[
    ("28:08","32:18"),
]
ffmpeg = r"C:\ffmpeg-4.2.2-win64-static\ffmpeg-4.2.2-win64-static\bin\ffmpeg.exe"
temp_dir_name = "temp_movie_cutting"
RUN_COMMANDS=True
DELETE_FOLDER = False
OVERWRITE = True

def secs(t):
    try:
        date_time = datetime.datetime.strptime(t, "%H:%M:%S")
    except:
        date_time = datetime.datetime.strptime(t, "%M:%S")
    a_timedelta = date_time - datetime.datetime(1900, 1, 1)
    return int(a_timedelta.total_seconds())


def create_command(list_of_cuts, input_file="inputfile.mp4", output_file=None, run=True, temp_dir_name=temp_dir_name):
    temp_dir = Path(input_file).parent / temp_dir_name
    print("TEMP DIR", temp_dir)
    if output_file is None:
        output_file = Path(input_file).parent / (Path(input_file).stem + "_cut" + Path(input_file).suffix)

    final_cuts = [0]
    for cut1, cut2 in list_of_cuts:
        final_cuts.extend([secs(cut1),secs(cut2)])
    final_cuts.append(10000000)

    cut_v = []; cut_a = [];
    input_text = ""

    if run:
        Path(temp_dir).mkdir(exist_ok=True, parents=True)

    for cut_number in range(0, len(final_cuts), 2):
        i = int(cut_number/2)
        c1 = final_cuts[cut_number]
        c2 = final_cuts[cut_number + 1]
        temp_output_part_path = temp_dir / (f"part{i}"+Path(input_file).suffix)
        f = f"{ffmpeg} -i \"{input_file}\" -ss {c1} -t {c2}  -map 0 -c copy -map_metadata 0 -movflags use_metadata_tags \"{temp_output_part_path}\" -y"
        input_text += "file '" + str(temp_output_part_path) + "'\n"
        print("COMMAND", f)
        if run:
            if not OVERWRITE and temp_output_part_path.exists():
                ans = input("Overwrite? Y/n ")
            if not temp_output_part_path.exists() or OVERWRITE or ans.lower()=="y":
                result = subprocess.run(f, shell=True,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT)
                print("Result", result)


    inputs_file = temp_dir / "inputs.txt"
    if run:
        with inputs_file.open("w") as f:
            f.write(input_text)
    print(input_text)


    concat_command = f"{ffmpeg} -f concat -safe 0 -i \"{inputs_file}\" -map 0 -c copy -map_metadata 0 -movflags use_metadata_tags \"{output_file}\" -y"
    print(concat_command)
    if run:
        if not OVERWRITE and output_file.exists():
            ans=input("Overwrite? Y/n ")
        if not output_file.exists() or OVERWRITE or ans.lower()=="y":
            result = subprocess.run(concat_command, shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
            print("Result", result)

    if run and DELETE_FOLDER:
        shutil.rmtree(temp_dir)

c = create_command(list_of_cuts, input_file=input_file, run=RUN_COMMANDS)
print(c)

print("DONE!")