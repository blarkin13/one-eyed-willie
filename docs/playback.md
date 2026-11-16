# Playback, movie pages, and HLS

One-Eyed Willie 0.13.0 opens each movie on `/movie?library_id=…&key=…` with a poster, description, backdrop, watched state, and fullscreen Play button. It does not change the media files.

## Playback modes

- Direct Play: FFprobe caches the actual file/container codecs. The browser checks its supported codec strings, while Google TV checks Android's decoder list. Compatible MKV and transport-stream sources may direct-play on Android. HTTP byte ranges are supported.
- Compatibility: when the device cannot handle the container or video/audio codec, FFmpeg produces H.264/AAC HLS segments. Safari has native HLS; other modern browsers use the pinned Apache-licensed Hls.js client (version 1.7.4). Hls.js currently loads from a public CDN, so those browsers require internet access to load the library.
- Streaming occurs **only** from the NUC origin, not Cloudflare Workers. Remote use requires the existing password-protected direct HTTPS address.
- Progress persists in the local SQLite database. Movies and TV episodes can be marked watched/unwatched.

## Play, Resume and Continue Watching

Movie and episode pages now use two compact icon actions: Play always begins at the start, and Resume appears when saved playback progress is at least 30 seconds and below 95% of the title. The same 30-second threshold determines whether a movie or episode appears in Continue Watching. The player saves position periodically and on closing. A completed title or one marked watched no longer appears there.

## Subtitles

The player now exposes a **CC** dropdown when compatible subtitle tracks exist. "CC Off" is the default. Supported external sidecars are `.srt`, `.vtt`, `.ass`, and `.ssa`, named alongside the video, for example:

```
The Goonies (1985).mkv
The Goonies (1985).en.srt
The Goonies (1985).forced.srt
```

Embedded text subtitle tracks (SubRip, ASS/SSA, mov_text, WebVTT) are also detected. FFmpeg converts them into browser WebVTT tracks and caches the results under `/data/subtitles`. Original files are not changed. Image-based subtitles such as PGS/VobSub are **not yet supported**; they require another approach (bitmap overlay or burn-in). Select CC Off to disable subtitles. HLS restarts request subtitles aligned to the resumed stream start time.

Subtitle endpoints are located under `/api/stream/subtitles/`, which the Cloudflare Worker blocks. Subtitles, like media bytes, are delivered only from the protected direct NUC origin.

## Optional Intel graphics acceleration

Standard Docker Compose continues to work with **CPU transcoding**. The updater now preserves the remote/HTTPS Compose profile and enables the Intel GPU overlay when /dev/dri/renderD128 is present. Inside the container, One-Eyed Willie tests that VAAPI actually encodes before using it; an unusable GPU falls back to software. GPU mode decodes in software and encodes H.264 on VAAPI so that unsupported source hardware decoders do not force full CPU encoding.

On an Intel NUC with Intel VAAPI hardware encoding, run on the NUC:

```bash
ls -l /dev/dri/renderD128
stat -c '%g' /dev/dri/renderD128
```

If that device exists, set `WILLIE_RENDER_GID` to the second command's output when launching the container with the GPU overlay:

```bash
cd /opt/one-eyed-willie/app
export WILLIE_RENDER_GID="$(stat -c '%g' /dev/dri/renderD128)"
sudo --preserve-env=WILLIE_RENDER_GID docker compose -f compose.remote.yaml -f compose.gpu.yaml up -d --build
```

The updater preserves the existing remote/HTTPS configuration and checks the render device automatically. After an update, inspect the live container device binding and test an actual transcode; code checks do not prove the host's Intel driver supports your files.

HLS segments are stored in `/data/hls/`, never in the media library. Only two concurrent sessions are allowed; inactive sessions are removed after 30 minutes. An HLS EVENT playlist retains generated segments for seeking and reads up to 1.5× real time ahead, rather than deleting 4-second segments from a tiny sliding playlist. The server stops streaming if disk space is low. Seeking within buffered HLS content stays in the existing session; otherwise the client requests a new session at the seek position. Neither HLS nor failed playback modifies the original media files.

## Testing

1. Verify `/health` is v0.13.0.
2. On the LAN, open a movie and select Play. Confirm fullscreen, sound, and timeline.
3. Try one MKV or HEVC movie, using the fallback. Confirm playback, 10-second skips, and resume.
4. Mark a movie watched, reload its page, and mark it unwatched.
5. Test an episode and check Continue Watching.
6. Test remote only through the direct password-protected HTTPS host, not through the Worker stream.
7. For failure diagnostics, inspect `docker logs one-eyed-willie --tail 100`. Never post private media paths or passwords publicly.

Known limitations: Browser compatibility depends on supported codecs; audio/subtitle track selection and adaptive HLS ladders are not implemented yet. GPU acceleration requires driver and device permissions on the particular NUC.


## Playback acceptance checklist (server and Google TV)

- Confirm `/api/watch/{media_id}/status` includes `media.video_codec`, `media.audio_codec`, dimensions and container from FFprobe.
- On Google TV, direct-play a supported H.264 MP4 and HEVC MKV. If the TV lacks the codec, verify clean HLS fallback without losing the position.
- Repeat ten 10-second skips quickly, seek backward within buffered content, seek 20 minutes ahead, pause for 5 minutes and resume.
- Play an entire movie or >45-minute episode; confirm the server does not delete HLS segments while the client is using them.
- Confirm automatic updates preserve the active HTTPS deployment and `/dev/dri/renderD128` when available; test `h264_vaapi` inside the running container.
- Check concurrent playback limit, disk low guard, progress updates, captions, and remote HTTPS access.

GPU support and reliable playback must be validated against the actual NUC and TV; CI alone cannot exercise those devices.


## Google TV player controls and scrub previews

The native Google TV player now uses icon-based transport controls with visible D-pad focus, a larger progress bar and a thumbnail preview while scrubbing. Pressing the remote's rewind/fast-forward media buttons or left/right while the controls are hidden seeks by 10 seconds. With the timeline focused, left/right changes the seek position; a brief pause commits the target. Rapid skips are combined into one seek.

Preview images are **not** video decoder frames on the television. The server makes 24 read-only JPEG frames at timestamps spanning the video, on first playback if needed, with only one low-priority on-demand generator at a time. The player polls briefly while those frames are created; if video has no previews yet it displays the target timestamp and a loading message. Preview generation never changes the original media. The existing nightly maintenance preview setting can disable on-demand generation too.

Validation: play a TV episode, use the remote left/right keys, focus the timeline and scrub to the middle, pause and resume, select subtitles, navigate to the next episode, and verify the overlay hides during regular playback. First-play previews may become available progressively while the server generates them.
