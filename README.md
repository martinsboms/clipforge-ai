---
title: ClipForge AI
emoji: ✂️
colorFrom: purple
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# ClipForge AI — starter web app

ClipForge AI is a working starter application for processing videos into vertical clips. It uses:
- Streamlit for the browser UI
- yt-dlp for supported public video URLs (or upload a local video)
- faster-whisper for speech-to-text with word timestamps
- FFmpeg for 9:16 split-screen rendering, title cards and subtitles

## Important limitations (read before deploying)
1. **This is a first working MVP, not a fully autonomous human-level viral editor.** Moment ranking is currently heuristic (dialogue density, reaction words, punctuation and window length). It does not understand the visual story or guarantee viral performance.
2. The current renderer assumes the facecam is a rectangular area in the source video. Set its x/y/width/height in the sidebar. The gameplay panel is a center-cropped view of the full source. For streams where the facecam is already composited over gameplay, you may need to tune the facecam crop or use a source with a separate facecam track.
3. URL downloading depends on the source site's availability and terms. Only process videos you own or are authorized to download and republish. Some platforms block downloads or require cookies; this starter does not bypass access controls.
4. Long livestreams can exceed free-host memory, storage and execution limits. For best results, first test with a 10–30 minute source. A production version should use background workers and object storage.
5. The free CPU hosting option can be slow. The Whisper model downloads on first use.

## Run locally
Install Python 3.11 and FFmpeg, then:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open the local address printed by Streamlit. Upload an MP4 or paste a supported URL. Check the permission box and click **Find moments and create clips**.

## Recommended deployment: Streamlit Community Cloud (browser-only setup)

This is the best first deployment route because Streamlit Community Cloud currently offers free app hosting and supports `requirements.txt` plus Linux packages through `packages.txt`. It deploys from a GitHub repository. See the official docs: https://docs.streamlit.io/deploy/streamlit-community-cloud

1. Extract this ZIP on your iPhone using the Files app.
2. Create a GitHub account if you do not already have one, then create a **public** repository named `clipforge-ai`.
3. Upload the contents of the `clipforge_ai` folder into the repository's root (not the parent folder). Include `app.py`, `requirements.txt`, `packages.txt`, `README.md`, and the `.streamlit` folder if your uploader allows hidden folders. `Dockerfile` is not needed for Streamlit Community Cloud.
4. Open https://share.streamlit.io/ and sign in with GitHub.
5. Choose **Create app**, select the `clipforge-ai` repository, branch `main`, and main file path `app.py`, then deploy.
6. Wait for dependency installation and app startup. Open the generated `*.streamlit.app` address in Safari.

Streamlit's docs confirm that Community Cloud deploys from GitHub and installs external Linux dependencies listed in `packages.txt`: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies

**Important hosting limit:** free Community Cloud resources are limited and can change. The current documented maximum is about 2.7 GB RAM, so multi-hour streams may fail or run slowly. Start with a 10–20 minute test video. This app processes synchronously and is not yet a production job-queue system.

## Alternative: Hugging Face Docker Space

The included `Dockerfile` and README metadata are ready for a Docker Space. However, Hugging Face's current documentation says Docker Spaces on `cpu-basic` require a PRO subscription for personal accounts (or Team/Enterprise for organizations). Check current plan details before choosing this route: https://huggingface.co/docs/huggingface_hub/main/guides/manage-spaces

## iPhone workflow
- Open the deployed Space in Safari.
- Paste a supported video URL, or use the upload control to select a video from Files.
- Adjust the facecam crop sliders for the stream's layout.
- Start processing and download each MP4.
- Save finished clips to Files, then upload them to your publishing platform.

## Layout
- Output: 1080 × 1920 (9:16)
- Top facecam panel: 690 px (about 36%)
- Bottom gameplay panel: 1230 px (about 64%)
- White title card with black text
- Word-timed subtitles near the bottom

## Troubleshooting
- **URL fails:** download the source through an authorized method and upload the file.
- **No speech found:** try clearer audio or a supported language.
- **Facecam crop is wrong:** tune the four facecam sliders. The sliders are percentages of the original source frame.
- **Render fails:** test a shorter video; check FFmpeg is installed.
- **Space restarts:** free CPU hosting may run out of memory/time on long videos. Use shorter sources or upgrade compute.
