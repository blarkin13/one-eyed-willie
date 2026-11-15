# Playback, movie pages, and HLS

One-Eyed Willie 0.13.0 opens each movie on `/movie?library_id=…&key=…` with a poster, description, backdrop, watched state, and fullscreen Play button. It does not change the media files.

## Playback modes

- Direct Play: for common browser-supported MP4/WebM codecs, use the local indexed file with HTTP byte-range streaming.
- Compatibility: for MKV, AVI, unsupported video/audio codecs, and failed Direct Play, FFmpeg produces H.264/AAC HLS segments. Safari has native HLS; other modern browsers use the pinned Apache-licensed Hls.js client (version 1.7.4). Hls.js currently loads from a public CDN, so those browsers require internet access to load the library.
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

Standard Docker Compose continues to work with **CPU transcoding**. Hardware acceleration is not switched on automatically if the render device is unavailable in the container.

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

If you use the normal single-compose updater after this, it may recreate the container **without** the GPU overlay; the application then falls back to CPU safely. Configure the updater to include the GPU overlay once the hardware setup is validated. GPU encoding does not guarantee that every video codec can use hardware acceleration.

HLS segments are stored in `/data/hls/`, never in the media library. Only two concurrent sessions are allowed, and inactive sessions are removed after 3 minutes. The server stops streaming if disk space is low. Seeking outside the active HLS window starts a new HLS session at the requested time.

## Testing

1. Verify `/health` is v0.13.0.
2. On the LAN, open a movie and select Play. Confirm fullscreen, sound, and timeline.
3. Try one MKV or HEVC movie, using the fallback. Confirm playback, 10-second skips, and resume.
4. Mark a movie watched, reload its page, and mark it unwatched.
5. Test an episode and check Continue Watching.
6. Test remote only through the direct password-protected HTTPS host, not through the Worker stream.
7. For failure diagnostics, inspect `docker logs one-eyed-willie --tail 100`. Never post private media paths or passwords publicly.

Known limitations: Browser compatibility depends on supported codecs; audio/subtitle track selection and adaptive HLS ladders are not implemented yet. GPU acceleration requires driver and device permissions on the particular NUC.
