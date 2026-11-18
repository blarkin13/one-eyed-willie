// Temporary app hostname entry point. Until shared cross-host auth is implemented,
// use the existing signed-in /app route on the Yarr account origin.
// The redirect is deliberate: the __Host- session cookie is host-only.
const HOME='https://yarr.larki-brian.workers.dev';
export default {async fetch(request) {
 const u=new URL(request.url);
 if(request.method==='GET'&&u.pathname==='/health')return Response.json({service:'app-yarr',status:'preview',media_proxy:false},{headers:{'cache-control':'no-store'}});
 if(request.method!=='GET'&&request.method!=='HEAD')return new Response('Method not allowed',{status:405,headers:{'cache-control':'no-store'}});
 // Never forward request headers, bearer tokens, cookies, or arbitrary destinations.
 return new Response(null,{status:302,headers:{location:HOME+'/app','cache-control':'no-store','referrer-policy':'no-referrer'}});
}};
