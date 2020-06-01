# cleanvid

cleanvid is a little script to mute profanity in video files in a few simple steps:

1. The user provides as input a video file and matching .srt subtitle file. If subtitles are not provided, [`subliminal`](https://github.com/Diaoul/subliminal) is used to attempt to download the best matching .srt file.
2. [`pysrt`](https://github.com/byroot/pysrt) is used to parse the .srt file, and each entry is checked against a [list](swears.txt) of profanity or other words or phrases you'd like muted. Mappings can be provided (eg., map "sh*t" to "poop"), otherwise the word will be replaced with *****.
3. A new "clean" .srt file is created. with *only* those phrases containing the censored/replaced objectional language.
4. [`ffmpeg`](https://www.ffmpeg.org/) is used to create a cleaned video file. This file contains the original video stream, but the audio stream is muted during the segments containing objectional language. The audio stream is re-encoded as AAC and remultiplexed back together with the video.

You can then use your favorite media player to play the cleaned video file together with the cleaned srt file.

## Prerequisites

[cleanvid](cleanvid.py) requires:

* Python 3
* [FFmpeg](https://www.ffmpeg.org)
* [delegator.py](https://github.com/kennethreitz/delegator.py)
* [pysrt](https://github.com/byroot/pysrt)
* [subliminal](https://github.com/Diaoul/subliminal)

## usage

```
$ ./cleanvid.py --help
usage: cleanvid.py [-h] [-s <srt>] [-i <input video>] [-o <output video>]
                   [-w <profanity file>] [-l <language>]

optional arguments:
  -h, --help            show this help message and exit
  -s <srt>, --subs <srt>
                        .srt subtitle file (will attempt auto-download if
                        unspecified)
  -i <input video>, --input <input video>
                        input video file
  -o <output video>, --output <output video>
                        output video file
  -w <profanity file>, --swears <profanity file>
                        text file containing profanity (with optional mapping)
  -l <language>, --lang <language>
                        language for srt download (default is "eng")
```

## Contributing

If you'd like to help improve cleanvid, pull requests will be welcomed!

## Authors

* **Seth Grover** - *Initial work* - [mmguero](https://github.com/mmguero)

## License

This project is licensed under the Apache License, v2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

Thanks to:
* the developers of [FFmpeg](https://www.ffmpeg.org/about.html)
* [delegator.py](https://github.com/kennethreitz/delegator.py) developer Kenneth Reitz and contributors
* [pysrt](https://github.com/byroot/pysrt) developer Jean Boussier and contributors
* [subliminal](https://github.com/Diaoul/subliminal) developer Antoine Bertin and contributors

## Disclaimers

By using cleanvid you understand and agree that its author(s) are in no way responsible for your actions. If cleanvid borks your system, or if you download a "pirated" movie and SWAT team of the copyright office of your respective nation busts down your door with a flash-bang grenade, or if cleanvid censors too much or too little and your feelings get hurt, or whatever, well, that's on you, dog.
