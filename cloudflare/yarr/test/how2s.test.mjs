// node --test cloudflare/yarr/test/
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {loadWorker,makeEnv,request} from './harness.mjs';
import {HOW2S,HOW2_PATHS} from '../how2s.js';

const PUB='https://yarr.media';

test('guides index lists every guide inside the shared site header and footer', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const res=await request(worker,env,'GET',PUB+'/how2s');
 assert.equal(res.status,200);
 const page=await res.text();
 assert.match(page,/<header class="site-header"/);
 assert.match(page,/<footer class="site-footer"/);
 for(const g of HOW2S)assert.ok(page.includes('href="/how2s/'+g.slug+'"'),g.slug);
 assert.doesNotMatch(page,/news hosting|usenet provider/i);
});

test('every guide renders with chrome, pager and no broken internal guide links', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const slugs=new Set(HOW2S.map(g=>g.slug));
 for(const g of HOW2S){
  const res=await request(worker,env,'GET',PUB+'/how2s/'+g.slug);
  assert.equal(res.status,200,g.slug);
  const page=await res.text();
  assert.match(page,/<header class="site-header"/,g.slug);
  assert.match(page,/<footer class="site-footer"/,g.slug);
  assert.ok(page.includes('<h1>'+g.title+'</h1>'),g.slug);
  assert.match(page,/class="how2-pager"/);
  for(const [,slug] of page.matchAll(/href="\/how2s\/([a-z0-9-]+)/g))assert.ok(slugs.has(slug),g.slug+' links to missing guide '+slug);
  assert.doesNotMatch(page,/\*\*|\]\(/,g.slug+' has unrendered markup');
 }
});

test('download-app guides carry the rights note; trailing slash and unknown guides handled', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 for(const slug of ['sabnzbd','sonarr','radarr','lidarr','prowlarr']){
  const page=await (await request(worker,env,'GET',PUB+'/how2s/'+slug)).text();
  assert.match(page,/Only download media you have the rights to/,slug);
 }
 assert.equal((await request(worker,env,'GET',PUB+'/how2s/sonarr/')).status,200);
 const missing=await request(worker,env,'GET',PUB+'/how2s/nope');
 assert.equal(missing.status,303);
 assert.equal(missing.headers.get('location'),'/how2s');
});

test('guides are in the sitemap and the footer', async()=>{
 const worker=await loadWorker(),env=makeEnv();
 const map=await (await request(worker,env,'GET',PUB+'/sitemap.xml')).text();
 for(const p of HOW2_PATHS)assert.ok(map.includes('<loc>'+PUB+p+'</loc>'),p);
 const home=await (await request(worker,env,'GET',PUB+'/features')).text();
 assert.match(home,/href="https:\/\/yarr\.media\/how2s">Setup guides</);
});
