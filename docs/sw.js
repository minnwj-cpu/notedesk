/* 노트앱 서비스워커 — 앱 껍데기를 통째로 캐시한다. 판이 바뀌면 V 가 바뀌어 옛 캐시는 지운다 */
const V="notedesk-a461771481";
const SHELL=["./", "./index.html", "./vendor/jszip.min.js", "./sangdam/icon-180.png", "./sangdam/icon-192.png", "./gijil/", "./gijil/index.html", "./gijil/manifest.webmanifest", "./gijil/icon-180.png", "./gijil/icon-192.png", "./gijil/icon-512.png", "./josa/", "./josa/index.html", "./josa/manifest.webmanifest", "./josa/icon-180.png", "./josa/icon-192.png", "./josa/icon-512.png", "./sangdam/", "./sangdam/index.html", "./sangdam/manifest.webmanifest", "./sangdam/icon-512.png"];
self.addEventListener("install",e=>{
  e.waitUntil(caches.open(V).then(c=>c.addAll(SHELL.map(u=>new Request(u,{cache:"reload"})))).then(()=>self.skipWaiting()));
});
self.addEventListener("activate",e=>{
  e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==V).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
self.addEventListener("fetch",e=>{
  const req=e.request; if(req.method!=="GET") return;
  let url; try{ url=new URL(req.url); }catch(x){ return; }
  const same=url.origin===self.location.origin;
  const font=/(^|\.)fonts\.(googleapis|gstatic)\.com$/.test(url.hostname);
  if(!same&&!font) return;
  if(req.mode==="navigate"||(same&&/(\/|\.html?)$/.test(url.pathname))) e.respondWith(pageFirstNet(req));
  else e.respondWith(cacheFirst(req));
});
/* 화면(html): 네트워크 먼저 — 새 판이 바로 뜬다. 3초 안에 안 오거나 오프라인이면 캐시 */
async function pageFirstNet(req){
  const c=await caches.open(V);
  try{
    const ctrl=new AbortController(); const t=setTimeout(()=>ctrl.abort(),3000);
    const r=await fetch(req,{signal:ctrl.signal}); clearTimeout(t);
    if(r&&r.ok) c.put(req,r.clone());
    return r;
  }catch(err){
    const m=await c.match(req,{ignoreSearch:true}); if(m) return m;
    const dir=await c.match(new URL("./",req.url).href,{ignoreSearch:true}); if(dir) return dir;
    throw err;
  }
}
/* 그 밖(스크립트·아이콘·글꼴): 캐시 먼저, 없으면 받아서 담는다 */
async function cacheFirst(req){
  const c=await caches.open(V);
  const m=await c.match(req); if(m) return m;
  const r=await fetch(req);
  if(r&&(r.ok||r.type==="opaque")) c.put(req,r.clone());
  return r;
}
