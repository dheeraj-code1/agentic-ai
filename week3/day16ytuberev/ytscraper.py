#!/usr/bin/env python3
"""
Fetch transcripts for every video in a YouTube playlist and split them into
fixed 75-second chunks. Each chunk = {videoId, start, end, text, url}.

Install:
    pip install yt-dlp youtube-transcript-api

Usage:
    python yt_playlist_chunks.py "https://www.youtube.com/playlist?list=PLxxxx" -o chunks.jsonl
    python yt_playlist_chunks.py PLxxxx --chunk-seconds 75 --langs en hi
"""
import argparse
import json
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api import RequestBlocked


def playlist_id(playlist: str) -> str:
    playlist = playlist.strip()
    if not playlist.startswith("http"):
        return playlist
    query = parse_qs(urlparse(playlist).query)
    ids = query.get("list") or []
    if not ids or not ids[0]:
        raise SystemExit("Could not find a playlist id in that URL.")
    return ids[0]


def chunks_path(playlist: str) -> Path:
    return Path(f"chunks_{playlist_id(playlist)}.jsonl")


def playlist_url(playlist: str) -> str:
    playlist = playlist.strip()
    if playlist.startswith("http"):
        return playlist
    return f"https://www.youtube.com/playlist?list={playlist}"


def get_video_ids(playlist: str) -> list[str]:
    """Return video IDs for a playlist URL or bare playlist ID (no downloading)."""
    url = playlist_url(playlist)
    opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError:
        playlist_id = playlist.strip()
        hint = ""
        if playlist_id.startswith("PL") and not playlist_id.startswith("http") and len(playlist_id) != 34:
            hint = (
                f" This ID is {len(playlist_id)} characters; "
                "playlist IDs that start with PL are 34 characters, so one is probably missing."
            )
        raise SystemExit(
            f"Playlist not found: {url}\n"
            "YouTube returned 404. Copy the full link from the playlist page "
            f"(it looks like youtube.com/playlist?list=...).{hint}"
        )
    if not info:
        raise SystemExit(f"No videos found for {url}")
    return [e["id"] for e in (info.get("entries") or []) if e and e.get("id")]


def chunk_transcript(snippets, video_id: str, chunk_seconds: int = 75) -> list[dict]:
    """
    Group transcript snippets into fixed windows of `chunk_seconds`.
    A snippet goes into the window in which it STARTS.
    """
    buckets: dict[int, list[str]] = {}
    for s in snippets:
        idx = int(s.start // chunk_seconds)
        buckets.setdefault(idx, []).append(s.text.replace("\n", " ").strip())

    chunks = []
    for idx in sorted(buckets):
        start = idx * chunk_seconds
        text = " ".join(t for t in buckets[idx] if t).strip()
        if not text:
            continue
        chunks.append(
            {
                "videoId": video_id,
                "start": start,
                "end": start + chunk_seconds,
                "text": text,
                "url": f"https://youtu.be/{video_id}?t={start}",
            }
        )
    return chunks


def fetch_transcript(api: YouTubeTranscriptApi, video_id: str, langs: list[str]):
    """Fetch a transcript, treating en as a match for en-US and the same for other languages."""
    listing = list(api.list(video_id))
    for lang in langs:
        want = lang.lower().replace("_", "-")
        exact = [item for item in listing if item.language_code.lower().replace("_", "-") == want]
        regional = [
            item
            for item in listing
            if item.language_code.lower().replace("_", "-").startswith(want + "-")
        ]
        match = exact or regional
        if match:
            return match[0].fetch()
    return api.fetch(video_id, languages=langs)


def saved_video_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ids.add(json.loads(line)["videoId"])
            except (json.JSONDecodeError, KeyError):
                continue
    return ids


def get_ytube_playlist_chunks(playlist: str,chunk_seconds: int = 75,langs: list[str] = ["en"],sleep: float = 1.0):
    video_ids = get_video_ids(playlist)
    output = chunks_path(playlist)
    done = saved_video_ids(output)
    pending = [vid for vid in video_ids if vid not in done]
    print(f"Found {len(video_ids)} videos, {len(done)} already saved, {len(pending)} left")
    if not pending:
        print(f"Using existing {output}")
        return

    api = YouTubeTranscriptApi()
    total = 0
    with open(output, "a", encoding="utf-8") as f:
        for i, vid in enumerate(pending, 1):
            for attempt in range(4):
                try:
                    transcript = fetch_transcript(api, vid, langs)
                    chunks = chunk_transcript(transcript.snippets, vid, chunk_seconds)
                    for c in chunks:
                        f.write(json.dumps(c, ensure_ascii=False) + "\n")
                    f.flush()
                    total += len(chunks)
                    print(f"[{i}/{len(pending)}] {vid}: {len(chunks)} chunks")
                    break
                except RequestBlocked:
                    if attempt == 3:
                        print(
                            "YouTube blocked this IP. Saved chunks are kept. "
                            "Stop and run again later; already saved videos are skipped."
                        )
                        print(f"{total} new chunks written to {output}")
                        return
                    wait = 30 * (2 ** attempt)
                    print(f"[{i}/{len(pending)}] {vid}: IP blocked, waiting {wait}s")
                    time.sleep(wait)
                except Exception as e:  # no captions, disabled, private, etc.
                    print(f"[{i}/{len(pending)}] {vid}: skipped ({type(e).__name__})")
                    break
            time.sleep(sleep)

    print(f"Done. {total} new chunks written to {output}")


def download_audio(video_id: str, audio_dir: Path) -> Path:
    audio_dir.mkdir(parents=True, exist_ok=True)
    existing = [path for path in audio_dir.glob(f"{video_id}.*") if not path.name.endswith(".part")]
    if existing:
        return existing[0]

    opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": str(audio_dir / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    saved = [path for path in audio_dir.glob(f"{video_id}.*") if not path.name.endswith(".part")]
    if not saved:
        raise RuntimeError(f"No audio file saved for {video_id}")
    return saved[0]


def transcribe_to_english(model, audio_path: Path) -> list[tuple[float, str]]:
    """Whisper translate writes English text even when the audio is Hindi or Hinglish."""
    segments, _info = model.transcribe(str(audio_path), task="translate", beam_size=1)
    cues = []
    for segment in segments:
        text = segment.text.replace("\n", " ").strip()
        if text:
            cues.append((float(segment.start), text))
    return cues


def chunk_cues(cues: list[tuple[float, str]], video_id: str, chunk_seconds: int = 75) -> list[dict]:
    buckets: dict[int, list[str]] = {}
    for start, text in cues:
        buckets.setdefault(int(start // chunk_seconds), []).append(text)

    chunks = []
    for idx in sorted(buckets):
        start = idx * chunk_seconds
        text = " ".join(part for part in buckets[idx] if part).strip()
        if not text:
            continue
        chunks.append(
            {
                "videoId": video_id,
                "start": start,
                "end": start + chunk_seconds,
                "text": text,
                "url": f"https://youtu.be/{video_id}?t={start}",
            }
        )
    return chunks


def get_ytube_playlist_chunks_whisper(
    playlist: str,
    chunk_seconds: int = 75,
    model_name: str = "small",
    sleep: float = 1.0,
    limit: int | None = None,
):
    """Download audio and translate it to English with Whisper, then save 75-second chunks."""
    from faster_whisper import WhisperModel

    video_ids = get_video_ids(playlist)
    output = chunks_path(playlist)
    done = saved_video_ids(output)
    pending = [vid for vid in video_ids if vid not in done]
    if limit is not None:
        pending = pending[:limit]
    print(f"Found {len(video_ids)} videos, {len(done)} already saved, {len(pending)} to transcribe")
    if not pending:
        print(f"Using existing {output}")
        return

    print(f"Loading Whisper model {model_name} on CPU")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    audio_dir = Path("audio")
    total = 0
    with open(output, "a", encoding="utf-8") as f:
        for i, vid in enumerate(pending, 1):
            try:
                audio_path = download_audio(vid, audio_dir)
                print(f"[{i}/{len(pending)}] {vid}: translating {audio_path.name}")
                chunks = chunk_cues(transcribe_to_english(model, audio_path), vid, chunk_seconds)
                for chunk in chunks:
                    f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                f.flush()
                total += len(chunks)
                print(f"[{i}/{len(pending)}] {vid}: {len(chunks)} chunks")
            except Exception as e:
                print(f"[{i}/{len(pending)}] {vid}: skipped ({type(e).__name__}: {e})")
            time.sleep(sleep)

    print(f"Done. {total} new chunks written to {output}")