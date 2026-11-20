// Owner-only statistics. Count known public pages only; never record identifiers or query strings.
export async function recordPublicPage(env,path){
 if(env.YARR_OWNER_ANALYTICS_ENABLED!=='true'||!env.ACCOUNTS)return;
 try{await env.ACCOUNTS.prepare("INSERT INTO owner_site_daily(day,path,requests) VALUES(date('now'),?,1) ON CONFLICT(day,path) DO UPDATE SET requests=requests+1").bind(path).run();}catch{}
}
export async function readSiteStats(env){
 if(env.YARR_OWNER_ANALYTICS_ENABLED!=='true')return null;
 try{return await env.ACCOUNTS.prepare("SELECT COALESCE(SUM(requests),0) AS total,MIN(day) AS first_day FROM owner_site_daily WHERE day>=date('now','-29 days')").first();}catch{return null;}
}
export async function readReleaseStats(env,fetcher=fetch){
 if(env.YARR_OWNER_ANALYTICS_ENABLED!=='true')return null;
 try{
  const response=await fetcher('https://api.github.com/repos/blarkin13/one-eyed-willie/releases?per_page=100',{headers:{'Accept':'application/vnd.github+json','User-Agent':'Yarr-Media-Owner'},cf:{cacheTtl:300,cacheEverything:true},signal:AbortSignal.timeout(5000)});
  if(!response.ok)return null;
  const data=await response.json();if(!Array.isArray(data))return null;
  const counts={tv:0,android:0,linux:0,installer:0};
  for(const release of data){if(release.draft||release.prerelease)continue;for(const a of release.assets||[]){
   const n=a.download_count;if(!Number.isSafeInteger(n)||n<0)continue;
   if(/google-tv\.apk$/i.test(a.name))counts.tv+=n;
   else if(/android\.apk$/i.test(a.name))counts.android+=n;
   else if(/\.deb$/i.test(a.name))counts.linux+=n;
   else if(a.name==='install.sh')counts.installer+=n;
  }}
  return counts;
 }catch{return null;}
}
