// Yarr multi-user account control plane. Staging only; no media proxy or public login.
const JSON_HEADERS = {
  'content-type': 'application/json; charset=utf-8',
  'cache-control': 'no-store',
  'x-content-type-options': 'nosniff',
  'referrer-policy': 'no-referrer',
  'content-security-policy': "default-src 'none'; frame-ancestors 'none'"
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'GET' && (url.pathname === '/health' || url.pathname === '/__edge/health')) {
      let database = 'unavailable';
      try {
        await env.ACCOUNTS.prepare('SELECT 1 AS ok').first();
        database = 'ready';
      } catch (_) {
        // Do not expose D1 errors or account details to unauthenticated clients.
      }
      return new Response(JSON.stringify({
        service: 'yarr',
        status: 'staging',
        database,
        authentication: 'not_configured',
        media_proxy: false
      }), {status: database === 'ready' ? 200 : 503, headers: JSON_HEADERS});
    }
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/auth/')) {
      return new Response(JSON.stringify({
        error: 'not_configured',
        message: 'Account sign-in is not enabled. No media servers are exposed.'
      }), {status: 503, headers: JSON_HEADERS});
    }
    return new Response(JSON.stringify({
      service: 'yarr',
      status: 'staging',
      message: 'Account service foundation. Sign-in and public access are not yet enabled.'
    }), {status: 200, headers: JSON_HEADERS});
  }
};
