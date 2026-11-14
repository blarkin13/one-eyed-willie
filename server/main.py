from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="One-Eyed Willie", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "application": "one-eyed-willie", "version": "0.1.0"}


@app.get("/", response_class=HTMLResponse)
def home():
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>One-Eyed Willie</title>
  <style>
    body { background:#111318; color:#f5f6f9; font:16px system-ui,sans-serif;
           min-height:100vh; display:grid; place-items:center; margin:0; }
    main { text-align:center; padding:2rem; }
    h1 { font-size:clamp(2rem,6vw,4rem); margin:0 0 .5rem; }
    p { color:#a8adb8; }
  </style>
</head>
<body><main><h1>One-Eyed Willie</h1><p>Your media. Your library.</p>
<p>Server is running. Library management is coming next.</p></main></body>
</html>"""
