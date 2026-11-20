import {test} from 'node:test';
import assert from 'node:assert/strict';
import {loadWorker,makeEnv,request} from './harness.mjs';
import {HOW2_PATHS} from '../how2s.js';

const PUB='https://yarr.media';
const routes=['/','/features','/free-vs-pro','/remote-access','/how-it-works',
 '/apt','/terms','/privacy','/cookies',...HOW2_PATHS];

test('every public page has consistent colored YARR.MEDIA branding and unique canonical SEO tags',async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const titles=new Set(),descriptions=new Set();
 for(const path of routes){
  const res=await request(worker,env,'GET',PUB+path);
  assert.equal(res.status,200,path);
  const html=await res.text();
  assert.match(html,/<span class="site-brand-label">YARR<span class="brand-dot">\.<\/span><span class="brand-media">MEDIA<\/span><\/span>/,path);
  assert.match(html,/\.site-header \.site-brand \.brand-dot\{color:#9b9b9b!important\}/,path);
  assert.match(html,/\.site-header \.site-brand \.brand-media\{color:#c62838!important\}/,path);
  const tags={
   canonical:[...html.matchAll(/<link rel="canonical" href="([^"]+)">/g)].map(m=>m[1]),
   title:[...html.matchAll(/<title>([^<]+)<\/title>/g)].map(m=>m[1]),
   description:[...html.matchAll(/<meta name="description" content="([^"]+)">/g)].map(m=>m[1]),
   ogTitle:[...html.matchAll(/<meta property="og:title" content="([^"]+)">/g)].map(m=>m[1]),
   ogDescription:[...html.matchAll(/<meta property="og:description" content="([^"]+)">/g)].map(m=>m[1]),
   ogURL:[...html.matchAll(/<meta property="og:url" content="([^"]+)">/g)].map(m=>m[1]),
   ogImage:[...html.matchAll(/<meta property="og:image" content="([^"]+)">/g)].map(m=>m[1]),
   twitterTitle:[...html.matchAll(/<meta name="twitter:title" content="([^"]+)">/g)].map(m=>m[1]),
   jsonld:[...html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)].map(m=>m[1])
  };
  for(const [key,values] of Object.entries(tags))assert.equal(values.length,1,path+' '+key);
  assert.equal(tags.canonical[0],PUB+path,path);
  assert.equal(tags.ogURL[0],PUB+path,path);
  assert.ok(tags.description[0].length>=50,path+' description');
  assert.ok(!titles.has(tags.title[0]),path+' duplicate title');
  assert.ok(!descriptions.has(tags.description[0]),path+' duplicate description');
  titles.add(tags.title[0]);descriptions.add(tags.description[0]);
  const data=JSON.parse(tags.jsonld[0]);
  assert.equal(data['@context'],'https://schema.org',path);
  assert.ok(data['@graph'].find(x=>x['@type']==='WebPage'||x['@type']==='CollectionPage'),path);
  if(path.startsWith('/how2s/'))assert.ok(data['@graph'].find(x=>x['@type']==='TechArticle'),path);
  if(path==='/')assert.ok(data['@graph'].find(x=>x['@type']==='SoftwareApplication'),path);
 }
});

test('sitemap contains exactly indexable pages and private account remains noindex',async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const map=await (await request(worker,env,'GET',PUB+'/sitemap.xml')).text();
 for(const path of routes)assert.ok(map.includes('<loc>'+PUB+path+'</loc>'),path);
 assert.doesNotMatch(map,/accounts\.yarr\.media|\/account<\/loc>|\/app<\/loc>/);
 const account=await (await request(worker,env,'GET','https://accounts.yarr.media/')).text();
 assert.match(account,/<meta name="robots" content="noindex,nofollow">/);
 assert.doesNotMatch(account,/<link rel="canonical" href="https:\/\/yarr\.media\/">/);
 assert.doesNotMatch(account,/application\/ld\+json/);
 const robots=await (await request(worker,env,'GET',PUB+'/robots.txt')).text();
 assert.match(robots,/Sitemap: https:\/\/yarr\.media\/sitemap\.xml/);
 const privateRobots=await (await request(worker,env,'GET','https://accounts.yarr.media/robots.txt')).text();
 assert.match(privateRobots,/Disallow: \//);
});

test('launch and pricing pages describe downloadable software and one-time Pro accurately',async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const homepage=await (await request(worker,env,'GET',PUB+'/')).text();
 assert.match(homepage,/\$29 one-time, plus applicable tax/);
 assert.match(homepage,/Yarr Media downloads are available/);
 assert.doesNotMatch(homepage,/Pricing to be announced|Public downloads and Pro purchases are not yet available/);
 const terms=await (await request(worker,env,'GET',PUB+'/terms')).text();
 assert.match(terms,/\$29 USD one-time purchase/);
 assert.doesNotMatch(terms,/recurring subscription billed through Stripe/);
});
