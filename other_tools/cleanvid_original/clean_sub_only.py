import argparse
import base64
import chardet
import codecs
import errno
import json
import os
import shutil
import sys
import re
import pysrt
import delegator
from subliminal import *
from babelfish import Language

try:
    from cleanvid.caselessdictionary import CaselessDictionary
except ImportError:
    from caselessdictionary import CaselessDictionary
from itertools import tee

from cleanvid import GetSubtitles, VidCleaner

class VidCleaner(object):
    inputVidFileSpec = ""
    inputSubsFileSpec = ""
    cleanSubsFileSpec = ""
    edlFileSpec = ""
    tmpSubsFileSpec = ""
    assSubsFileSpec = ""
    outputVidFileSpec = ""
    swearsFileSpec = ""
    swearsPadMillisec = 0
    embedSubs = False
    fullSubs = False
    subsOnly = False
    edl = False
    hardCode = False
    reEncode = False
    unalteredVideo = False
    subsLang = SUBTITLE_DEFAULT_LANG
    vParams = VIDEO_DEFAULT_PARAMS
    aParams = AUDIO_DEFAULT_PARAMS
    plexAutoSkipJson = ""
    plexAutoSkipId = ""
    swearsMap = CaselessDictionary({})
    muteTimeList = []

    ######## init #################################################################

    def __init__(
        self,
        iVidFileSpec,
        iSubsFileSpec,
        oVidFileSpec,
        oSubsFileSpec,
        iSwearsFileSpec,
        swearsPadSec=0,
        embedSubs=False,
        fullSubs=False,
        subsOnly=False,
        edl=False,
        subsLang=SUBTITLE_DEFAULT_LANG,
        reEncode=False,
        hardCode=False,
        vParams=VIDEO_DEFAULT_PARAMS,
        aParams=AUDIO_DEFAULT_PARAMS,
        plexAutoSkipJson="",
        plexAutoSkipId="",
    ):

        if (iVidFileSpec is not None) and os.path.isfile(iVidFileSpec):
            self.inputVidFileSpec = iVidFileSpec
        else:
            raise IOError(errno.ENOENT, os.strerror(errno.ENOENT), iVidFileSpec)

        if (iSubsFileSpec is not None) and os.path.isfile(iSubsFileSpec):
            self.inputSubsFileSpec = iSubsFileSpec

        if (iSwearsFileSpec is not None) and os.path.isfile(iSwearsFileSpec):
            self.swearsFileSpec = iSwearsFileSpec
        else:
            raise IOError(errno.ENOENT, os.strerror(errno.ENOENT), iSwearsFileSpec)

        if (oVidFileSpec is not None) and (len(oVidFileSpec) > 0):
            self.outputVidFileSpec = oVidFileSpec
            if os.path.isfile(self.outputVidFileSpec):
                os.remove(self.outputVidFileSpec)

        if (oSubsFileSpec is not None) and (len(oSubsFileSpec) > 0):
            self.cleanSubsFileSpec = oSubsFileSpec
            if os.path.isfile(self.cleanSubsFileSpec):
                os.remove(self.cleanSubsFileSpec)

        self.swearsPadMillisec = swearsPadSec * 1000
        self.embedSubs = embedSubs
        self.fullSubs = fullSubs
        self.subsOnly = subsOnly or edl or (plexAutoSkipJson and plexAutoSkipId)
        self.edl = edl
        self.plexAutoSkipJson = plexAutoSkipJson
        self.plexAutoSkipId = plexAutoSkipId
        self.reEncode = reEncode
        self.hardCode = hardCode
        self.subsLang = subsLang
        self.vParams = vParams
        self.aParams = aParams
        if self.vParams.startswith('base64:'):
            self.vParams = base64.b64decode(self.vParams[7:]).decode('utf-8')
        if self.aParams.startswith('base64:'):
            self.aParams = base64.b64decode(self.aParams[7:]).decode('utf-8')


def RunCleanvid():
    command = f"-i {} --subs {} --subs-only"
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-s',
        '--subs',
        help='.srt subtitle file (will attempt auto-download if unspecified and not --offline)',
        metavar='<srt>',
    )
    parser.add_argument('-i', '--input', required=True, help='input video file', metavar='<input video>')
    parser.add_argument(
        '--plex-auto-skip-id',
        help='content identifier for PlexAutoSkip (also implies --subs-only)',
        metavar='<content identifier>',
        dest="plexAutoSkipId",
    )
    parser.add_argument('--subs-output', help='output subtitle file', metavar='<output srt>', dest="subsOut")
    parser.add_argument(
        '-w',
        '--swears',
        help='text file containing profanity (with optional mapping)',
        default=os.path.join(__script_location__, 'swears.txt'),
        metavar='<profanity file>',
    )
    parser.add_argument(
        '-l',
        '--lang',
        help=f'language for srt download (default is "{SUBTITLE_DEFAULT_LANG}")',
        default=SUBTITLE_DEFAULT_LANG,
        metavar='<language>',
    )
    parser.add_argument(
        '-p', '--pad', help='pad (seconds) around profanity', metavar='<int>', dest="pad", type=int, default=1
    )
    parser.add_argument(
        '-e',
        '--embed-subs',
        help='embed subtitles in resulting video file',
        dest='embedSubs',
        action='store_true',
    )
    parser.add_argument(
        '-f',
        '--full-subs',
        help='include all subtitles in output subtitle file (not just scrubbed)',
        dest='fullSubs',
        action='store_true',
    )
    parser.add_argument(
        '--subs-only',
        help='only operate on subtitles (do not alter audio)',
        dest='subsOnly',
        action='store_true',
    )
    parser.add_argument(
        '--offline',
        help="don't attempt to download subtitles",
        dest='offline',
        action='store_true',
    )
    parser.add_argument(
        '--edl',
        help='generate MPlayer EDL file with mute actions (also implies --subs-only)',
        dest='edl',
        action='store_true',
    )
    parser.add_argument('-r', '--re-encode', help='Re-encode video', dest='reEncode', action='store_true')
    parser.add_argument(
        '-b', '--burn', help='Hard-coded subtitles (implies re-encode)', dest='hardCode', action='store_true'
    )
    parser.add_argument(
        '-v',
        '--video-params',
        help='Video parameters for ffmpeg (only if re-encoding)',
        dest='vParams',
        default=VIDEO_DEFAULT_PARAMS,
    )
    parser.add_argument(
        '-a', '--audio-params', help='Audio parameters for ffmpeg', dest='aParams', default=AUDIO_DEFAULT_PARAMS
    )
    parser.set_defaults(
        embedSubs=False,
        fullSubs=False,
        subsOnly=False,
        offline=False,
        reEncode=False,
        hardCode=False,
        edl=False,
    )
    args = parser.parse_args()

    inFile = args.input
    outFile = args.output
    subsFile = args.subs
    lang = args.lang
    plexFile = args.plexAutoSkipJson
    if inFile:
        inFileParts = os.path.splitext(inFile)
        if not outFile:
            outFile = inFileParts[0] + "_clean" + inFileParts[1]
        if not subsFile:
            subsFile = GetSubtitles(inFile, lang, args.offline)
        if args.plexAutoSkipId and not plexFile:
            plexFile = inFileParts[0] + "_PlexAutoSkip_clean.json"

    if plexFile and not args.plexAutoSkipId:
        raise ValueError(
            f'Content ID must be specified if creating a PlexAutoSkip JSON file (https://github.com/mdhiggins/PlexAutoSkip/wiki/Identifiers)'
        )

    cleaner = VidCleaner(
        inFile,
        subsFile,
        outFile,
        args.subsOut,
        args.swears,
        args.pad,
        args.embedSubs,
        args.fullSubs,
        args.subsOnly,
        args.edl,
        lang,
        args.reEncode,
        args.hardCode,
        args.vParams,
        args.aParams,
        plexFile,
        args.plexAutoSkipId,
    )
    cleaner.CreateCleanSubAndMuteList()
    cleaner.MultiplexCleanVideo()
