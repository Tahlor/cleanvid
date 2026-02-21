from pathlib import Path
import datetime
import time
from typing import Literal

def secs(atime):
    if ":" in atime:
        x = time.strptime(atime.split('.')[0],'%H:%M:%S')
        return int(datetime.timedelta(hours=x.tm_hour,minutes=x.tm_min,seconds=x.tm_sec).total_seconds())
    return atime

def construct_ffmpeg_trim_cmd(timepairs,
                              inpath,
                              outpath,
                              mode: Literal["cut","keep"]="cut",
                              gpu=False,
                              codec:Literal["libx265","libx264","hevc_nvenc"]="libx265"):
    """
    GPU h265 is faster, but the compression size/quality ratio is worse than libx265
    Args:
        timepairs:
        inpath:
        outpath:
        mode: cut-delete time pairs
              keep-keep only timepairs

    Returns:

    """
    if gpu:
        gpu = "-hwaccel cuda "
        codec = "hevc_nvenc"

    cmd = f'ffmpeg {gpu} -i "{str(inpath)}" -y -filter_complex '

    cmd += '"'
    if mode=="cut":
        _timepairs = ["0"]
        for x in timepairs:
            _timepairs.extend(x)
        _timepairs += [""]
        timepairs = [_timepairs[2*n:2*n+2] for n,_ in enumerate(_timepairs[::2])]
        print(timepairs)

    for i, (start, end) in enumerate(timepairs):
        _end=f":end={secs(end)}" if end else ""
        _start=f"start={secs(start)}" if start else ""

        cmd += (f"[0:v]trim={_start}{_end},setpts=PTS-STARTPTS[{i}v]; " +
                f"[0:a]atrim={_start}{_end},asetpts=PTS-STARTPTS[{i}a]; ") # ,format=yuv420p[{i}v]
    for i, (start, end) in enumerate(timepairs):
        cmd += f"[{i}v][{i}a]"
    cmd += f'concat=n={len(timepairs)}:v=1:a=1[outv][outa]'
    cmd += '"'
    cmd += f' -map [outv] -map [outa]  -c:v {codec} "{str(outpath)}"'
    """
    """
    return cmd

if __name__=='__main__':
    #root = J:\Media\Videos\Misc Videos\msc\Lightyear.2022.1080p.WEBRip.x265-RARBG"
    root = "/mnt/j/Media/Videos/Misc Videos/msc/Lightyear.2022.1080p.WEBRip.x265-RARBG"
    root = "."
    root = Path(root)
    times = [["00:17:40","00:18:00"],["00:21:26","00:21:31"],["00:21:56","00:22:00"],["00:22:16","00:22:23"]]

    #,["5","00:00:08"],]
    inp = root / "_.mp4"
    out = root / "out.mp4"
    x = construct_ffmpeg_trim_cmd(times, inp, out, mode="cut")
    print(x)


"""
ffmpeg -hwaccel cuda -c:v libx265 -i "_.mp4" -y -filter_complex "[0:v]trim=start=0:end=1058,setpts=PTS-STARTPTS[0v]; [0:a]atrim=start=0:end=1058,asetpts=PTS-STARTPTS[0a]; [0:v]trim=start=1080:end=1286,setpts=PTS-STARTPTS[1v]; [0:a]atrim=start=1080:end=1286,asetpts=PTS-STARTPTS[1a]; [0:v]trim=start=1291:end=1316,setpts=PTS-STARTPTS[2v]; [0:a]atrim=start=1291:end=1316,asetpts=PTS-STARTPTS[2a]; [0:v]trim=start=1320:end=1336,setpts=PTS-STARTPTS[3v]; [0:a]atrim=start=1320:end=1336,asetpts=PTS-STARTPTS[3a]; [0:v]trim=start=1343,setpts=PTS-STARTPTS[4v]; [0:a]atrim=start=1343,asetpts=PTS-STARTPTS[4a]; [0v][0a][1v][1a][2v][2a][3v][3a][4v][4a]concat=n=5:v=1:a=1[outv][outa]" -map [outv] -map [outa] "out.mp4"


ffmpeg -hwaccel cuda -c:v libx265 -i "~/Videos/_.mp4" -y -filter_complex "[0:v]trim=start=0:end=1058,setpts=PTS-STARTPTS[0v]; [0:a]atrim=start=0:end=1058,asetpts=PTS-STARTPTS[0a]; [0:v]trim=start=1080:end=1286,setpts=PTS-STARTPTS[1v]; [0:a]atrim=start=1080:end=1286,asetpts=PTS-STARTPTS[1a]; [0:v]trim=start=1291:end=1316,setpts=PTS-STARTPTS[2v]; [0:a]atrim=start=1291:end=1316,asetpts=PTS-STARTPTS[2a]; [0:v]trim=start=1320:end=1336,setpts=PTS-STARTPTS[3v]; [0:a]atrim=start=1320:end=1336,asetpts=PTS-STARTPTS[3a]; [0:v]trim=start=1343,setpts=PTS-STARTPTS[4v]; [0:a]atrim=start=1343,asetpts=PTS-STARTPTS[4a]; [0v][0a][1v][1a][2v][2a][3v][3a][4v][4a]concat=n=5:v=1:a=1[outv][outa]" -map [outv] -map [outa] "~/Videos/out.mp4"

"""