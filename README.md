# VidClean

VidClean is tool to mute profanity in video files:

1. Create a Google Cloud developer account. New members often recieve $300 in credits for the first year, in addition to free monthly allotments.
    * Create a project - https://console.cloud.google.com/iam-admin
    * Enable the required APIs - https://console.developers.google.com/apis
    
            Cloud Speech-to-Text API
            Cloud Storage					
            Google Cloud Storage JSON API
            Cloud Video Intelligence API
             
    * Download a credential JSON - https://console.cloud.google.com/apis/credentials/serviceaccountkey        
        Choose the correct project, create new user, select an administrative role (e.g. "Project -> Owner"), save the JSON file.
              
2. [`ffmpeg`](https://www.ffmpeg.org/) is used to create a cleaned video file, intall it.
3. Configure the...config. At a minimum, the path to the video and credential json are required. 

## Run
    python D:\Github\cleanvid\clean_audio.py --video [path]
    or
    python "D:\Github\cleanvid\clean_audio.py" /config/path

## To Do: 
* Expand to filter graphic content using "Cloud Video Intelligence API"
* Alternatively, use subtitles + forced alignment, or some opensource alternative.

## Resources:
* Free Trial:
    https://console.cloud.google.com/freetrial/signup/tos

* Cloud Storage:
    https://console.cloud.google.com/storage/browser?pli=1

* Video:
    * Billing: https://cloud.google.com/video-intelligence/pricing   
    * Info: https://cloud.google.com/video-intelligence/docs/analyze-safesearch
* Audio: 
    * Billing: https://cloud.google.com/speech-to-text/pricing
    * Info: https://cloud.google.com/speech-to-text/docs/
 
* Billing:
    * https://console.cloud.google.com/billing

## License

This project is licensed under the Apache License, v2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

Thanks to:
* the developers of [FFmpeg](https://www.ffmpeg.org/about.html)
* [delegator.py](https://github.com/kennethreitz/delegator.py) developer Kenneth Reitz and contributors
* [subliminal](https://github.com/Diaoul/subliminal) developer Antoine Bertin and contributors
* [cleanvid](https://github.com/mmguero/cleanvid/) developer Seth Grover and contributors
