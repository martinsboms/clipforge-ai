import os, re, json, math, shutil, subprocess, tempfile, time
from pathlib import Path
import streamlit as st
import pandas as pd
import numpy as np
from faster_whisper import WhisperModel
import yt_dlp

APP_DIR = Path("/tmp/clipforge")
WORK = APP_DIR / "work"
OUT = APP_DIR / "clips"
WORK.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="ClipForge AI", page_icon="✂️", layout="wide")
st.title("✂️ ClipForge AI")
st.caption("Turn long livestreams into short-form clips — automatically.")

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout)[-4000:])
    return p.stdout

def probe(path):
    raw = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-show_entries", "stream=width,height", "-of", "json", str(path)])
    data = json.loads(raw)
    video = next(s for s in data.get("streams", []) if "width" in s)
    return float(data["format"]["duration"]), int(video["width"]), int(video["height"])

def download_url(url, target):
    opts = {
        "outtmpl": str(target),
        "format": "best[height<=1080]/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 2,
        "fragment_retries": 2,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    if target.exists():
        return target
    candidates = list(target.parent.glob(target.stem + ".*"))
    if not candidates:
        raise RuntimeError("Download did not produce a video file.")
    return candidates[0]

@st.cache_resource(show_spinner="Loading speech recognition model…")
def load_whisper():
    # CPU int8 keeps the starter deployment affordable. First run downloads model weights.
    return WhisperModel("base", device="cpu", compute_type="int8")

def transcribe(path):
    model = load_whisper()
    segments, info = model.transcribe(str(path), word_timestamps=True, vad_filter=True,
                                      beam_size=3, condition_on_previous_text=False)
    result = []
    for seg in segments:
        words = []
        if seg.words:
            for w in seg.words:
                words.append({"start": float(w.start), "end": float(w.end), "text": w.word.strip()})
        result.append({"start": float(seg.start), "end": float(seg.end),
                       "text": seg.text.strip(), "words": words})
    return result, info.language

HOOK_WORDS = {
    "no way": 5, "what": 1, "wait": 2, "bro": 1, "oh my": 3, "crazy": 3,
    "insane": 3, "run": 2, "help": 2, "look": 2, "why": 1, "how": 1,
    "seriously": 2, "oh": 1, "wow": 3, "damn": 2, "stop": 2, "sorry": 1,
    "laugh": 2, "killed": 2, "die": 1, "fight": 2, "never": 2, "actually": 1
}

def make_candidates(segments, duration, min_len=22, max_len=48):
    # Sliding windows; score speech energy, reaction language, questions and punctuation.
    candidates = []
    step = 12
    start = 0.0
    while start < duration:
        end = min(start + max_len, duration)
        if end - start < min_len:
            break
        chosen = [s for s in segments if s["end"] > start and s["start"] < end]
        text = " ".join(s["text"] for s in chosen).strip()
        if len(text.split()) >= 12:
            low = text.lower()
            keyword_score = sum(weight for phrase, weight in HOOK_WORDS.items() if phrase in low)
            exclaims = text.count("!") * 1.2
            questions = text.count("?") * 1.0
            words = len(text.split())
            speech_density = min(words / 45, 2.0)
            # Reward moments with a clear conversational arc, not just loud words.
            duration_score = 1.0 if 25 <= end-start <= 45 else 0.4
            score = keyword_score + exclaims + questions + speech_density + duration_score
            candidates.append({"start": start, "end": end, "text": text,
                               "score": round(score, 2), "words": words})
        start += step
    candidates.sort(key=lambda x: x["score"], reverse=True)
    # Remove heavily overlapping candidates so the shortlist contains distinct moments.
    picked = []
    for c in candidates:
        if all(min(c["end"], p["end"]) - max(c["start"], p["start"]) < 12 for p in picked):
            picked.append(c)
        if len(picked) >= 20:
            break
    return picked

def clean_title(text, limit=58):
    text = re.sub(r"\s+", " ", text).strip(" .!?,-")
    words = text.split()
    title = " ".join(words[:10])
    if len(title) > limit:
        title = title[:limit].rsplit(" ", 1)[0]
    return title.upper() if title else "YOU WON'T BELIEVE THIS"

def ass_time(seconds):
    h = int(seconds // 3600); m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def make_ass(segments, clip_start, clip_end, title, output):
    # ASS uses separate title and subtitle styles. Subtitles are placed in the lower safe area.
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,Arial,54,&H00000000,&H000000FF,&H00000000,&H00FFFFFF,-1,0,3,2,0,8,65,65,1140,1
Style: Sub,Arial,58,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,1,4,2,2,90,90,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    title_end = min(3.8, clip_end - clip_start)
    title = title.replace("\\", "").replace("{", "").replace("}", "")
    lines.append(f"Dialogue: 1,0:00:00.00,{ass_time(title_end)},Title,,0,0,0,,{title}")
    for seg in segments:
        words = [w for w in seg["words"] if w["end"] > clip_start and w["start"] < clip_end]
        if not words:
            continue
        # 4–6 word chunks for readable, synced captions.
        for i in range(0, len(words), 5):
            chunk = words[i:i+5]
            if not chunk: continue
            stt = max(0, chunk[0]["start"] - clip_start)
            enn = min(clip_end-clip_start, chunk[-1]["end"] - clip_start + 0.12)
            txt = " ".join(w["text"] for w in chunk).strip()
            txt = txt.replace("{", "").replace("}", "").replace("\\", "")
            if txt and enn > stt:
                lines.append(f"Dialogue: 0,{ass_time(stt)},{ass_time(enn)},Sub,,0,0,0,,{txt}")
    output.write_text(header + "\n".join(lines), encoding="utf-8")

def render_clip(video, candidate, idx, face_x, face_y, face_w, face_h, title):
    dur, width, height = probe(video)
    start, end = candidate["start"], candidate["end"]
    clip_dur = end - start
    # Coordinates are normalized percentages of the source frame.
    fx, fy = int(width*face_x), int(height*face_y)
    fw, fh = max(2, int(width*face_w)), max(2, int(height*face_h))
    fx = max(0, min(fx, width-fw)); fy = max(0, min(fy, height-fh))
    # Gameplay crop defaults to a central 16:9 source crop; it remains user-adjustable by source framing.
    ass = WORK / f"clip_{idx}.ass"
    make_ass([], start, end, title, ass)  # replaced below with full transcript events by caller
    out = OUT / f"clipforge_{idx:02d}.mp4"
    # Top facecam is 36%; gameplay is 64%. Both are fitted to a 1080px canvas.
    filter_complex = (
        f"[0:v]split=2[facein][gamein];"
        f"[facein]crop={fw}:{fh}:{fx}:{fy},scale=1080:690:force_original_aspect_ratio=increase,"
        f"crop=1080:690[face];"
        f"[gamein]scale=1080:1230:force_original_aspect_ratio=increase,crop=1080:1230[game];"
        f"[face][game]vstack=inputs=2,subtitles='{str(ass).replace(':', r'\\:')}'[v]"
    )
    cmd = ["ffmpeg", "-y", "-ss", str(start), "-i", str(video), "-t", str(clip_dur),
           "-filter_complex", filter_complex, "-map", "[v]", "-map", "0:a?",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
    run(cmd)
    return out

def render_with_captions(video, candidate, idx, face_x, face_y, face_w, face_h, title, transcript):
    dur, width, height = probe(video)
    start, end = candidate["start"], candidate["end"]
    fx, fy = int(width*face_x), int(height*face_y)
    fw, fh = max(2, int(width*face_w)), max(2, int(height*face_h))
    fx = max(0, min(fx, width-fw)); fy = max(0, min(fy, height-fh))
    ass = WORK / f"clip_{idx}.ass"
    make_ass(transcript, start, end, title, ass)
    out = OUT / f"clipforge_{idx:02d}.mp4"
    ass_path = str(ass).replace("\\", "/").replace(":", r"\:")
    fc = (
        f"[0:v]split=2[facein][gamein];"
        f"[facein]crop={fw}:{fh}:{fx}:{fy},scale=1080:690:force_original_aspect_ratio=increase,"
        f"crop=1080:690[face];"
        f"[gamein]scale=1080:1230:force_original_aspect_ratio=increase,crop=1080:1230[game];"
        f"[face][game]vstack=inputs=2,subtitles='{ass_path}'[v]"
    )
    run(["ffmpeg", "-y", "-ss", str(start), "-i", str(video), "-t", str(end-start),
         "-filter_complex", fc, "-map", "[v]", "-map", "0:a?",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)])
    return out

def save_upload(upload):
    path = WORK / upload.name
    path.write_bytes(upload.getbuffer())
    return path

with st.sidebar:
    st.header("Clip settings")
    st.write("Your reference layout: streamer above, gameplay below.")
    face_x = st.slider("Facecam left position (%)", 0, 90, 0) / 100
    face_y = st.slider("Facecam top position (%)", 0, 90, 0) / 100
    face_w = st.slider("Facecam width (%)", 10, 100, 35) / 100
    face_h = st.slider("Facecam height (%)", 10, 100, 35) / 100
    n_clips = st.slider("Number of clips to export", 1, 10, 5)
    min_len = st.slider("Minimum clip length (seconds)", 15, 40, 22)
    max_len = st.slider("Maximum clip length (seconds)", 30, 60, 48)
    st.caption("Set the facecam crop once to match the stream layout. The gameplay uses the remaining full-frame source.")

st.subheader("1. Add your livestream or video")
url = st.text_input("Video URL", placeholder="Paste a supported public video URL")
upload = st.file_uploader("Or upload a video file", type=["mp4", "mov", "mkv", "webm"])
authorized = st.checkbox("I have permission to download, edit and publish this video.")
start_btn = st.button("🚀 Find moments and create clips", type="primary", use_container_width=True)

if start_btn:
    if not authorized:
        st.error("Please confirm you have permission to process and publish this footage.")
        st.stop()
    if not url and not upload:
        st.error("Paste a video URL or upload a video file.")
        st.stop()
    try:
        with st.status("Preparing source video…", expanded=True) as status:
            if upload:
                source = save_upload(upload)
            else:
                source = download_url(url, WORK / "source.mp4")
            duration, w, h = probe(source)
            st.write(f"Loaded {duration/60:.1f} minutes · {w} × {h}")
            status.update(label="Transcribing audio…", state="running")
            transcript, language = transcribe(source)
            st.write(f"Detected language: {language}. Transcript segments: {len(transcript)}")
            status.update(label="Finding promising moments…", state="running")
            candidates = make_candidates(transcript, duration, min_len, max_len)
            if not candidates:
                raise RuntimeError("I couldn't find enough spoken content to rank. Try a video with clearer speech.")
            st.write(f"Found {len(candidates)} distinct candidate moments.")
            status.update(label="Rendering vertical clips…", state="running")
            results = []
            for i, c in enumerate(candidates[:n_clips], 1):
                title = clean_title(c["text"])
                path = render_with_captions(source, c, i, face_x, face_y, face_w, face_h,
                                            title, transcript)
                results.append((c, title, path))
                st.write(f"Rendered clip {i}/{min(n_clips, len(candidates))}")
            status.update(label="Your clips are ready", state="complete")
        st.success(f"Created {len(results)} clips.")
        st.subheader("2. Your selected moments")
        rows = []
        for i, (c, title, path) in enumerate(results, 1):
            rows.append({"Clip": i, "Start": time.strftime("%H:%M:%S", time.gmtime(c["start"])),
                         "End": time.strftime("%H:%M:%S", time.gmtime(c["end"])),
                         "Score": c["score"], "Suggested hook": title})
            with st.expander(f"Clip {i}: {title}", expanded=(i == 1)):
                st.write(f"**Source time:** {rows[-1]['Start']} – {rows[-1]['End']}  ·  **Score:** {c['score']}")
                st.write(c["text"])
                st.video(str(path))
                st.download_button("Download MP4", data=path.read_bytes(),
                                   file_name=path.name, mime="video/mp4", key=f"dl_{i}")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.info("Clip scores are heuristic estimates, not predictions or guarantees of virality. Review clips before publishing.")
    except Exception as e:
        st.error(f"Processing failed: {e}")
        st.caption("If the URL cannot be downloaded, upload a video file you are authorized to use. Long streams may exceed the memory/time limits of free hosting.")
else:
    st.markdown("#### Your workflow")
    st.markdown("**Paste link or upload → Transcribe → Rank moments → Render clips → Download MP4**")
    st.caption("First run can take longer while the speech model downloads. Large livestreams need substantial processing time.")
