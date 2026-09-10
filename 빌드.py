# -*- coding: utf-8 -*-
r"""
노트앱 사이트 빌드 — src\*.html (앱 원본) → docs\ (GitHub Pages 가 올리는 폴더)

  python 빌드.py

만드는 것
  docs\index.html                  세 앱으로 가는 첫 화면
  docs\<app>\index.html            앱 본체 (PWA 머리말 + 내려받기 표준화 + 서비스워커 등록)
  docs\<app>\manifest.webmanifest  홈 화면 앱 이름·아이콘
  docs\<app>\icon-*.png            아이콘
  docs\vendor\jszip.min.js         zip 풀기 (오프라인용 로컬 사본)
  docs\sw.js                       서비스워커 — 앱 껍데기를 통째로 캐시, 오프라인에서도 열린다
"""
import hashlib, io, json, re, shutil, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent
SRC, DOCS, VENDOR = ROOT / "src", ROOT / "docs", ROOT / "vendor"

APPS = [
    dict(dir="gijil",   src="gijil-note.html",   name="기일노트", ch="기", color="#2C4E7A", desc="법정 — 제출 기록 · 기일 노트 · 쟁점 · 숙제"),
    dict(dir="josa",    src="josa-note.html",    name="조사노트", ch="조", color="#1F5F5B", desc="조사실 — 브리핑 · 예상문답 · 기록 · 열람"),
    dict(dir="sangdam", src="sangdam-note.html", name="상담노트", ch="상", color="#7A3B5C", desc="상담실 — 검토보고서 · 자료 · 질문 · 녹음"),
]

# claude.ai 아티팩트가 씌우던 껍데기와 같은 초기화 — 화면이 아티팩트 판과 똑같이 나온다
RESET_CSS = ("<style>:root{color-scheme:light}body{margin:0;padding:0;font:14px -apple-system,BlinkMacSystemFont,sans-serif;"
             "background:#faf9f5;color:#141413}img{max-width:100%}[hidden]:not([hidden=until-found]){display:none!important}</style>")

# 표준 브라우저용 내려받기 + 서비스워커 등록.  아티팩트 안에서는 window.claude.downloads 를 썼지만 여기는 최상위 문서다.
BOOT_JS = r"""
<script>
(function(){
  function blobOf(filename,data){
    if(data instanceof Blob) return data;
    if(data instanceof ArrayBuffer||ArrayBuffer.isView(data)) return new Blob([data]);
    var ext=(String(filename).split(".").pop()||"").toLowerCase();
    var mt={md:"text/markdown",ics:"text/calendar",txt:"text/plain",json:"application/json",csv:"text/csv",html:"text/html"}[ext]||"application/octet-stream";
    return new Blob([String(data)],{type:mt+";charset=utf-8"});
  }
  function viaAnchor(blob,filename){
    var u=URL.createObjectURL(blob), a=document.createElement("a");
    a.href=u; a.download=filename; a.rel="noopener"; a.style.display="none";
    document.body.appendChild(a); a.click();
    setTimeout(function(){ a.remove(); URL.revokeObjectURL(u); },60000);
  }
  window.__stdDownloads={
    save:function(o){
      var filename=o.filename, blob=blobOf(filename,o.data);
      var touch=("ontouchstart" in window)||navigator.maxTouchPoints>0;
      var file=null; try{ file=new File([blob],filename,{type:blob.type||"application/octet-stream"}); }catch(e){}
      /* 아이패드: 공유 시트로 — 「파일에 저장」·드라이브 앱으로 바로 보낸다. 취소하면 declined */
      if(touch&&file&&navigator.share&&navigator.canShare&&navigator.canShare({files:[file]})){
        return navigator.share({files:[file],title:filename}).then(function(){ return {ok:true}; })
          .catch(function(e){
            if(e&&e.name==="AbortError"){ var err=new Error("취소"); err.code="declined"; throw err; }
            viaAnchor(blob,filename); return {ok:true};
          });
      }
      viaAnchor(blob,filename); return Promise.resolve({ok:true});
    }
  };
  if("serviceWorker" in navigator){
    window.addEventListener("load",function(){
      navigator.serviceWorker.register("__SW__").catch(function(e){ console.warn("serviceWorker",e); });
    });
  }
})();
</script>
"""

def head(name, color, sw_rel, app_dir=True):
    icon = "./" if app_dir else "./sangdam/"   # 첫 화면은 상담노트 아이콘을 빌려 쓴다
    return f"""<!doctype html><html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{name}</title>
{('<link rel="manifest" href="./manifest.webmanifest">' if app_dir else '')}
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="{name}">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="theme-color" content="{color}">
<link rel="apple-touch-icon" href="{icon}icon-180.png">
<link rel="icon" type="image/png" sizes="192x192" href="{icon}icon-192.png">
{RESET_CSS}{BOOT_JS.replace("__SW__", sw_rel)}</head><body>
"""

def strip_wrapper(s):
    """아티팩트에서 읽어 온 판이면 껍데기(<!doctype…<body>)와 꼬리(</body></html>)를 벗긴다."""
    m = re.match(r"\s*<!doctype html><html><head>.*?</head><body>\s*", s, re.S | re.I)
    if m: s = s[m.end():]
    s = re.sub(r"\s*</body>\s*</html>\s*$", "\n", s, flags=re.I)
    return s

def stamp_of(s):
    m = re.search(r"Desk · ([0-9][0-9.a-z]*)", s)
    return m.group(1) if m else ""

def build_app(a):
    s = io.open(SRC / a["src"], encoding="utf-8").read()
    s = strip_wrapper(s)
    # 머리말은 head 에 있으니 본문 머리의 charset·title 은 뺀다
    s = re.sub(r'^\s*<meta charset="utf-8">\s*', "", s)
    s = re.sub(r'^\s*<title>[^<]*</title>\s*', "", s)
    n = s.count('<script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>')
    assert n == 1, f"{a['src']}: jszip 스크립트 태그 {n}개"
    s = s.replace('<script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>',
                  '<script src="../vendor/jszip.min.js"></script>')
    n = s.count("let downloads=null;")
    assert n == 1, f"{a['src']}: 'let downloads=null;' {n}개"
    s = s.replace("let downloads=null;", "let downloads=window.__stdDownloads||null;")
    out = DOCS / a["dir"]
    out.mkdir(parents=True, exist_ok=True)
    io.open(out / "index.html", "w", encoding="utf-8", newline="\n").write(head(a["name"], a["color"], "../sw.js") + s + "\n</body></html>\n")
    manifest = dict(name=a["name"], short_name=a["name"], description=a["desc"], lang="ko",
                    start_url="./", scope="./", display="standalone", orientation="any",
                    background_color="#faf9f5", theme_color=a["color"],
                    icons=[dict(src="icon-192.png", sizes="192x192", type="image/png"),
                           dict(src="icon-512.png", sizes="512x512", type="image/png", purpose="any maskable")])
    io.open(out / "manifest.webmanifest", "w", encoding="utf-8").write(json.dumps(manifest, ensure_ascii=False, indent=1))
    make_icons(out, a)
    return stamp_of(s)

def make_icons(out, a):
    from PIL import Image, ImageDraw, ImageFont
    for size in (180, 192, 512):
        im = Image.new("RGBA", (size, size), a["color"])
        d = ImageDraw.Draw(im)
        # 살짝 밝은 띠 — 셋을 나란히 두었을 때 구분되게
        d.rectangle([0, int(size * .78), size, size], fill=_mix(a["color"], "#FFFFFF", .16))
        font = ImageFont.truetype(r"C:\Windows\Fonts\malgunbd.ttf", int(size * .56))
        bb = d.textbbox((0, 0), a["ch"], font=font)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        d.text(((size - w) / 2 - bb[0], (size * .78 - h) / 2 - bb[1]), a["ch"], font=font, fill="#FFFFFF")
        small = ImageFont.truetype(r"C:\Windows\Fonts\malgun.ttf", int(size * .11))
        lb = a["name"]
        bb = d.textbbox((0, 0), lb, font=small)
        d.text(((size - (bb[2] - bb[0])) / 2 - bb[0], size * .78 + (size * .22 - (bb[3] - bb[1])) / 2 - bb[1]), lb, font=small, fill="#FFFFFF")
        im.convert("RGB").save(out / f"icon-{size}.png", optimize=True)

def _mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]; b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))

def launcher(stamps):
    cards = "".join(f"""
  <a class="card" href="./{a['dir']}/" style="--c:{a['color']}">
    <img src="./{a['dir']}/icon-192.png" alt="" width="64" height="64">
    <div><b>{a['name']}</b><span>{a['desc']}</span><i>{stamps.get(a['dir'],'')}</i></div>
  </a>""" for a in APPS)
    body = f"""
<style>
body{{background:#F3F0EE;color:#1F1B1D;font-family:"Noto Sans KR",'Apple SD Gothic Neo','Malgun Gothic',system-ui,sans-serif;padding:max(24px,env(safe-area-inset-top)) 20px 40px}}
.wrap{{max-width:560px;margin:0 auto}}
h1{{font-size:22px;margin:8px 0 2px}} p.sub{{margin:0 0 22px;color:#6E6468;font-size:13.5px}}
.card{{display:flex;gap:16px;align-items:center;background:#fff;border:1px solid #DAD2D0;border-left:6px solid var(--c);border-radius:12px;padding:14px 16px;margin:10px 0;text-decoration:none;color:inherit}}
.card img{{border-radius:14px;flex:0 0 64px}} .card b{{display:block;font-size:18px}} .card span{{display:block;font-size:13px;color:#6E6468;margin-top:2px}}
.card i{{display:block;font-style:normal;font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#9A9095;margin-top:4px}}
.how{{margin-top:26px;font-size:13.5px;line-height:1.7;color:#3A3236;background:#fff;border:1px solid #DAD2D0;border-radius:12px;padding:14px 16px}}
.how b{{color:#1F1B1D}}
</style>
<div class="wrap">
  <h1>노트앱</h1>
  <p class="sub">기일노트 · 조사노트 · 상담노트 — 각 앱을 열어 홈 화면에 따로 넣으세요.</p>
  {cards}
  <div class="how"><b>홈 화면에 넣기</b> — 앱을 연 뒤 사파리의 공유 버튼 → 「홈 화면에 추가」. 한 번 열어 두면 그 뒤로는 네트워크 없이도 열립니다.<br>
  <b>팩 넣기</b> — 앱 안의 「팩 열기」 → 파일 앱 → 구글 드라이브.<br>
  <b>마이크</b> — 상담노트 녹음은 처음 한 번 마이크 허용을 묻습니다.</div>
</div>
"""
    return head("노트앱", "#7A3B5C", "./sw.js", app_dir=False) + body + "</body></html>\n"

SW_JS = r"""/* 노트앱 서비스워커 — 앱 껍데기를 통째로 캐시한다. 판이 바뀌면 V 가 바뀌어 옛 캐시는 지운다 */
const V="__V__";
const SHELL=__SHELL__;
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
"""

def main():
    if DOCS.exists():
        for p in DOCS.iterdir():
            if p.name == ".nojekyll": continue
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    DOCS.mkdir(exist_ok=True)
    (DOCS / ".nojekyll").write_text("")          # GitHub Pages 가 파일을 손대지 않게
    (DOCS / "vendor").mkdir()
    shutil.copy(VENDOR / "jszip.min.js", DOCS / "vendor" / "jszip.min.js")
    stamps = {}
    for a in APPS:
        stamps[a["dir"]] = build_app(a)
        print(f"  {a['name']:5s} {a['dir']:8s} {stamps[a['dir']]}")
    io.open(DOCS / "index.html", "w", encoding="utf-8", newline="\n").write(launcher(stamps))
    # 서비스워커: 껍데기 목록 + 내용 해시로 판 번호
    shell = ["./", "./index.html", "./vendor/jszip.min.js", "./sangdam/icon-180.png", "./sangdam/icon-192.png"]
    for a in APPS:
        d = a["dir"]
        shell += [f"./{d}/", f"./{d}/index.html", f"./{d}/manifest.webmanifest", f"./{d}/icon-180.png", f"./{d}/icon-192.png", f"./{d}/icon-512.png"]
    shell = sorted(set(shell), key=shell.index)
    h = hashlib.sha1()
    for p in sorted(DOCS.rglob("*")):
        if p.is_file() and p.name != "sw.js": h.update(p.relative_to(DOCS).as_posix().encode()); h.update(p.read_bytes())
    v = "notedesk-" + h.hexdigest()[:10]
    io.open(DOCS / "sw.js", "w", encoding="utf-8", newline="\n").write(SW_JS.replace("__V__", v).replace("__SHELL__", json.dumps(shell, ensure_ascii=False)))
    print(f"  sw.js {v} · 껍데기 {len(shell)}개")
    print(f"빌드 끝 → {DOCS}")
    return stamps

if __name__ == "__main__":
    main()
