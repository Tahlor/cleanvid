"""Optional OpenSubtitles REST candidate provider.

Uses only official service endpoints. Credentials are loaded from the local
process environment or asked for via a hidden prompt; never logged. No media
or transcript is uploaded. Search and download budgets are deliberately bounded.
"""
import getpass
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from difflib import SequenceMatcher

API = "https://api.opensubtitles.com/api/v1"
MAX_JSON = 3_000_000
MAX_SRT = 2_000_000


def official_url(link):
    parts = urllib.parse.urlsplit(link)
    host = (parts.hostname or "").lower()
    return (parts.scheme == "https" and not parts.username and not parts.password
            and any(host == d or host.endswith("."+d)
                    for d in ("opensubtitles.com","opensubtitles.org","osdb.link")))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Unexpected provider redirect; no credentials forwarded")


def _int(value):
    try:
        return int(value)
    except (TypeError,ValueError):
        return None


def normalize(title):
    return " ".join(re.findall(r"[a-z0-9]+",str(title or "").casefold()))


def ranked_candidates(rows, title, season, episode, video_name, parent_imdb=None):
    """Filter strict episode metadata first; then rank release evidence."""
    candidates=[]
    seen=set()
    for row in rows:
        a=row.get("attributes",{})
        f=a.get("feature_details",{})
        if (_int(f.get("season_number")) != season or _int(f.get("episode_number")) != episode):
            continue
        if parent_imdb:
            if _int(f.get("parent_imdb_id")) != _int(parent_imdb):
                continue
        elif normalize(f.get("parent_title")) != normalize(title):
            continue
        if a.get("language")!="en" or any(a.get(k) for k in
                    ("foreign_parts_only","ai_translated","machine_translated")):
            continue
        for item in a.get("files",[]):
            file_id=_int(item.get("file_id"))
            name=str(item.get("file_name") or "")
            if file_id is None or file_id in seen or not name.lower().endswith(".srt"):
                continue
            release=str(a.get("release") or "")
            similarity=SequenceMatcher(None,normalize(video_name),normalize(release+" "+name)).ratio()
            score=100*bool(a.get("moviehash_match"))+20*similarity+4*bool(a.get("from_trusted"))+2*bool(a.get("hearing_impaired"))
            candidates.append(dict(file_id=file_id, score=score, release=release,
                                   name=name, hash_match=bool(a.get("moviehash_match"))))
            seen.add(file_id)
    return sorted(candidates,key=lambda c:(-c["score"],c["file_id"]))


class OpenSubtitles:
    def __init__(self, prompt=False):
        self.key=os.environ.get("OPENSUBTITLES_API_KEY")
        if not self.key:
            raise ValueError("OpenSubtitles app API key missing; use the official CLI instead")
        self.token=os.environ.get("OPENSUBTITLES_TOKEN")
        self.opener=urllib.request.build_opener(NoRedirect())
        self.last=0
        if not self.token:
            user=os.environ.get("OPENSUBTITLES_USERNAME")
            password=os.environ.get("OPENSUBTITLES_PASSWORD")
            if prompt:
                user=user or input("OpenSubtitles username: ").strip()
                password=password or getpass.getpass("OpenSubtitles password: ")
            if not user or not password:
                raise ValueError("OpenSubtitles login required; configure a token or use the secure login prompt")
            response=self.request("/login",body={"username":user,"password":password},auth=False)
            self.token=response.get("token")
            if not self.token:
                raise ValueError("OpenSubtitles login returned no token")
    def request(self,path,params=None,body=None,auth=True):
        if not path.startswith("/") or "?" in path:
            raise ValueError("Unsupported provider API path")
        wait=max(0,1.2-(time.monotonic()-self.last))
        time.sleep(wait)
        self.last=time.monotonic()
        url=API+path
        if params:
            url+="?"+urllib.parse.urlencode(sorted(params.items()))
        headers={"Api-Key":self.key,"User-Agent":"Cleanvid v1.0","Accept":"application/json"}
        if auth and self.token:
            headers["Authorization"]="Bearer "+self.token
        request=urllib.request.Request(url,headers=headers)
        if body is not None:
            request=urllib.request.Request(url,data=json.dumps(body).encode("utf-8"),
                                  headers={**headers,"Content-Type":"application/json"},method="POST")
        try:
            with self.opener.open(request,timeout=40) as response:
                raw=response.read(MAX_JSON+1)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"OpenSubtitles API returned HTTP {exc.code}; stop rather than retrying or bypassing limits") from None
        if len(raw)>MAX_JSON:
            raise ValueError("Provider JSON response is too large")
        return json.loads(raw)

    def search(self,video,title,season,episode,moviehash,parent_imdb=None):
        params={"languages":"en","season_number":season,"episode_number":episode,"foreign_parts_only":"exclude"}
        if parent_imdb:
            params["parent_imdb_id"]=int(str(parent_imdb).removeprefix("tt"))
        else:
            params["query"]=title.lower()
        rows=self.request("/subtitles",{**params,"moviehash":moviehash}).get("data",[])
        candidates=ranked_candidates(rows,title,season,episode,Path(video).stem,params.get("parent_imdb_id"))
        if len(candidates)<3:
            # Second bounded query without hash; same strict identity filters.
            rows+=self.request("/subtitles",params).get("data",[])
            candidates=ranked_candidates(rows,title,season,episode,Path(video).stem,params.get("parent_imdb_id"))
        return candidates

    def download(self,candidate,folder,video):
        folder=Path(folder)
        folder.mkdir(parents=True,exist_ok=True)
        # Stable unique name; never overwrite an existing candidate.
        path=folder/(Path(video).stem+".opensub-"+str(candidate["file_id"])+".en.srt")
        if path.exists():
            return path
        link=self.request("/download",body={"file_id":candidate["file_id"]}).get("link")
        if not link or not official_url(link):
            raise ValueError("Unexpected subtitle download host")
        # Separate request without API key, user credential or bearer token.
        try:
            with self.opener.open(urllib.request.Request(link,headers={"User-Agent":"Cleanvid v1.0"}),timeout=40) as response:
                data=response.read(MAX_SRT+1)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Subtitle download returned HTTP {exc.code}") from None
        if not data or len(data)>MAX_SRT:
            raise ValueError("Subtitle exceeds size limit")
        text=data.decode("utf-8-sig")
        if "-->" not in text or "\x00" in text:
            raise ValueError("Provider did not return a text SRT")
        with path.open("x",encoding="utf-8") as f:
            f.write(text)
        return path
