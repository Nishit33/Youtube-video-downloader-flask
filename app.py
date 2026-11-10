import copy
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from urllib.parse import urlparse

import yt_dlp
from flask import Flask, jsonify, render_template, request, send_file

app = Flask(__name__)

ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}

# All running / finished download jobs live here (job_id -> dict)
JOBS = {}
JOBS_LOCK = threading.Lock()
JOB_MAX_AGE = 60 * 60  # delete unfinished/unclaimed jobs after 1 hour

# Video details found in the "Check" step are saved here, so the "Download"
# step does not need to look the video up again (this saves several seconds).
INFO_CACHE = {}
INFO_CACHE_TTL = 20 * 60  # 20 minutes


def cache_info(url: str, info: dict):
    now = time.time()
    for key, (saved_at, _) in list(INFO_CACHE.items()):
        if now - saved_at > INFO_CACHE_TTL:
            INFO_CACHE.pop(key, None)
    INFO_CACHE[url] = (now, info)


def get_cached_info(url: str):
    entry = INFO_CACHE.get(url)
    if entry and time.time() - entry[0] <= INFO_CACHE_TTL:
        return copy.deepcopy(entry[1])
    return None


# ---------- helpers ----------
def is_youtube_url(url: str) -> bool:
    try:
        return urlparse(url).hostname in ALLOWED_HOSTS
    except ValueError:
        return False


def clean_error(exc: Exception) -> str:
    """Remove terminal colour codes from yt-dlp error messages."""
    text = re.sub(r"\x1b\[[0-9;]*m", "", str(exc))
    return text.replace("ERROR: ", "").strip()


def format_size(num_bytes: float) -> str:
    if not num_bytes:
        return ""
    mb = num_bytes / (1024 * 1024)
    return f"~{mb / 1024:.1f} GB" if mb >= 1024 else f"~{mb:.0f} MB"


def format_duration(seconds) -> str:
    if not seconds:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def purge_old_jobs():
    now = time.time()
    with JOBS_LOCK:
        for job_id, job in list(JOBS.items()):
            if now - job["created"] > JOB_MAX_AGE:
                shutil.rmtree(job["tmp_dir"], ignore_errors=True)
                del JOBS[job_id]


def build_options(quality: str, tmp_dir: str, progress_hook, pp_hook) -> dict:
    options = {
        "outtmpl": os.path.join(tmp_dir, "%(title).100s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        # speed: download in 10 MB chunks (avoids YouTube slow-down) and
        # fetch several fragments at the same time
        "http_chunk_size": 10 * 1024 * 1024,
        "concurrent_fragment_downloads": 8,
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [pp_hook],
    }

    if quality == "audio":
        options["format"] = "bestaudio/best"
        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        height = int(quality)
        # Best video up to the chosen height + best audio.
        options["format"] = f"bv*[height<={height}]+ba/b[height<={height}]"
        # Prefer: highest resolution -> H.264 (plays everywhere) -> highest fps -> AAC
        options["format_sort"] = ["res", "vcodec:h264", "fps", "acodec:aac"]
        # 1440p / 4K come as VP9/AV1, which fit better in MKV
        options["merge_output_format"] = "mp4" if height <= 1080 else "mkv"
        options["outtmpl"] = os.path.join(tmp_dir, "%(title).100s_%(height)sp.%(ext)s")

    return options


# ---------- background download ----------
def download_video(url: str, options: dict) -> dict:
    """Download using saved video details when possible (faster start)."""
    raw = get_cached_info(url)
    if raw is not None:
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                return ydl.process_ie_result(raw, download=True) or {}
        except Exception:
            pass  # saved details may be outdated -> look the video up again

    with yt_dlp.YoutubeDL(options) as ydl:
        raw = ydl.extract_info(url, download=False, process=False)
        return ydl.process_ie_result(raw, download=True) or {}


def run_job(job_id: str, url: str, quality: str):
    job = JOBS[job_id]
    streams = {}  # filename -> (downloaded_bytes, total_bytes)

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            streams[d["filename"]] = (d.get("downloaded_bytes", 0), total)
            done = sum(v[0] for v in streams.values())
            overall = sum(v[1] for v in streams.values())
            if overall:
                # never go backwards (video and audio are separate streams)
                job["percent"] = max(job["percent"], min(99.0, done / overall * 100))
            job["speed"] = d.get("speed")
            job["eta"] = d.get("eta")
            job["status"] = "downloading"
        elif d["status"] == "finished":
            size = d.get("total_bytes") or d.get("downloaded_bytes") or 0
            streams[d["filename"]] = (size, size)

    def pp_hook(d):
        if d["status"] == "started":
            job["status"] = "processing"

    try:
        options = build_options(quality, job["tmp_dir"], progress_hook, pp_hook)
        info = download_video(url, options)
        actual_height = info.get("height") or max(
            (f.get("height") or 0 for f in info.get("requested_formats", [])),
            default=0,
        )

        files = [
            f
            for f in os.listdir(job["tmp_dir"])
            if not f.endswith((".part", ".ytdl", ".temp"))
        ]
        if not files:
            raise RuntimeError("Download finished but no file was created.")
        files.sort(key=lambda f: os.path.getsize(os.path.join(job["tmp_dir"], f)))
        job["file"] = os.path.join(job["tmp_dir"], files[-1])
        if quality == "audio":
            job["quality_label"] = "MP3 audio"
        else:
            job["quality_label"] = f"{actual_height or quality}p"
        job["percent"] = 100.0
        job["status"] = "done"
    except Exception as exc:
        job["error"] = clean_error(exc)
        job["status"] = "error"


# ---------- routes ----------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/info", methods=["POST"])
def video_info():
    url = ((request.get_json(silent=True) or {}).get("url") or "").strip()
    if not is_youtube_url(url):
        return jsonify(error="Please enter a valid YouTube link."), 400

    try:
        with yt_dlp.YoutubeDL(
            {"quiet": True, "no_warnings": True, "noplaylist": True}
        ) as ydl:
            info = ydl.extract_info(url, download=False, process=False)
    except Exception as exc:
        return jsonify(error=clean_error(exc)), 400

    cache_info(url, copy.deepcopy(info))

    formats = info.get("formats", [])

    # size of the best audio stream (added to every video size)
    audio_size = max(
        (
            f.get("filesize") or f.get("filesize_approx") or 0
            for f in formats
            if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")
        ),
        default=0,
    )

    # every real resolution YouTube offers for this video
    sizes_by_height = {}
    for f in formats:
        height = f.get("height")
        if not height or f.get("vcodec") in (None, "none"):
            continue
        size = f.get("filesize") or f.get("filesize_approx") or 0
        sizes_by_height[height] = max(sizes_by_height.get(height, 0), size)

    qualities = [
        {
            "value": str(height),
            "label": f"{height}p",
            "size": format_size(size + audio_size) if size else "",
        }
        for height, size in sorted(sizes_by_height.items(), reverse=True)
    ]
    qualities.append(
        {"value": "audio", "label": "Audio only (MP3)", "size": format_size(audio_size)}
    )

    return jsonify(
        title=info.get("title", "Video"),
        thumbnail=f"https://i.ytimg.com/vi/{info.get('id')}/hqdefault.jpg",
        duration=format_duration(info.get("duration")),
        channel=info.get("uploader") or info.get("channel") or "",
        qualities=qualities,
    )


@app.route("/api/download", methods=["POST"])
def start_download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    quality = str(data.get("quality", ""))

    if not is_youtube_url(url):
        return jsonify(error="Please enter a valid YouTube link."), 400
    if quality != "audio" and not quality.isdigit():
        return jsonify(error="Invalid quality option."), 400

    purge_old_jobs()

    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "queued",
            "percent": 0.0,
            "speed": None,
            "eta": None,
            "error": None,
            "file": None,
            "quality_label": "",
            "tmp_dir": tempfile.mkdtemp(),
            "created": time.time(),
        }

    threading.Thread(target=run_job, args=(job_id, url, quality), daemon=True).start()
    return jsonify(job_id=job_id)


@app.route("/api/progress/<job_id>")
def progress(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify(error="Download not found."), 404

    speed = f"{job['speed'] / (1024 * 1024):.1f} MB/s" if job["speed"] else ""
    return jsonify(
        status=job["status"],
        percent=round(job["percent"], 1),
        speed=speed,
        eta=job["eta"],
        error=job["error"],
        quality=job["quality_label"],
    )


@app.route("/api/file/<job_id>")
def get_file(job_id):
    job = JOBS.get(job_id)
    if not job or job["status"] != "done":
        return jsonify(error="File is not ready."), 404

    response = send_file(
        job["file"], as_attachment=True, download_name=os.path.basename(job["file"])
    )

    def cleanup():
        shutil.rmtree(job["tmp_dir"], ignore_errors=True)
        with JOBS_LOCK:
            JOBS.pop(job_id, None)

    response.call_on_close(cleanup)
    return response


if __name__ == "__main__":
    app.run(debug=True)