// One-Eyed Willie control-plane proxy. Media streams must never flow through Workers.
// Set ORIGIN_URL in Cloudflare as an environment binding (HTTPS hostname only).
const NO_CACHE = { "cache-control": "no-store", "x-content-type-options": "nosniff" };

function unavailable() {
  return new Response("One-Eyed Willie: secure origin is not reachable yet. Finish HTTPS and router setup on vogsphere.", {
    status: 503, headers: { ...NO_CACHE, "content-type": "text/plain; charset=utf-8" }
  });
}
function blocked() {
  return new Response("Media must stream directly from the home server; Cloudflare Workers is for the library interface only.", {
    status: 403, headers: { ...NO_CACHE, "content-type": "text/plain; charset=utf-8" }
  });
}
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/__edge/health") {
      let originStatus = "not_configured";
      if (env.ORIGIN_URL) {
        try {
          const check = await fetch(new URL("/health", env.ORIGIN_URL), {
            method: "GET", redirect: "manual", signal: AbortSignal.timeout(4000),
            cf: { cacheTtl: 0 }
          });
          if (check.status === 401) originStatus = "reachable_protected";
          else if (check.status === 200) originStatus = "reachable_UNPROTECTED";
          else originStatus = "unexpected_status_" + check.status;
          check.body?.cancel();
        } catch (_) { originStatus = "unreachable"; }
      }
      return Response.json({
        edge: "ok",
        origin_status: originStatus,
        remote_server_verified: originStatus === "reachable_protected"
      }, { headers: NO_CACHE });
    }
    if (!["GET","HEAD","POST","PUT","PATCH","DELETE"].includes(request.method)) {
      return new Response("Method not allowed", { status: 405, headers: NO_CACHE });
    }
    if (request.headers.has("range") ||
        /^\/(api\/)?(stream|streams|play|playback|transcode|download|video|videos|audio|media)(\/|$)/i.test(url.pathname)) {
      return blocked();
    }
    if (!env.ORIGIN_URL) return unavailable();
    let base;
    try {
      base = new URL(env.ORIGIN_URL);
      if (base.protocol !== "https:" || base.username || base.password || base.search || base.hash || base.pathname !== "/" ||
          base.hostname === url.hostname) return unavailable();
    } catch (_) { return unavailable(); }
    const upstream = new URL(url.pathname + url.search, base);
    try {
      const headers = new Headers(request.headers);
      headers.delete("host");
      headers.delete("x-forwarded-host");
      headers.set("x-forwarded-host", url.hostname);
      const incoming = new Request(upstream, { method: request.method, headers,
        body: ["GET","HEAD"].includes(request.method) ? undefined : request.body,
        redirect: "manual" });
      const response = await fetch(incoming, { redirect: "manual", cf: { cacheTtl: 0 } });
      if (/^(video\/|audio\/|application\/octet-stream)/i.test(response.headers.get("content-type") || "")) {
        response.body?.cancel();
        return blocked();
      }
      const resultHeaders = new Headers(response.headers);
      const isArtwork = url.pathname.startsWith("/api/artwork/") &&
        response.ok && /^image\//i.test(response.headers.get("content-type") || "");
      // Browser-private image caching, while Cloudflare edge caching remains off.
      resultHeaders.set("cache-control",
        isArtwork ? "private, max-age=604800" : "no-store");
      const location = resultHeaders.get("location");
      if (location) {
        try {
          const redirect = new URL(location, upstream);
          if (redirect.origin === base.origin) {
            redirect.protocol = url.protocol;
            redirect.host = url.host;
            resultHeaders.set("location", redirect.toString());
          }
        } catch (_) { /* Preserve unrecognized redirect. */ }
      }
      return new Response(response.body, { status: response.status, statusText: response.statusText, headers: resultHeaders });
    } catch (_) {
      return unavailable();
    }
  }
};
