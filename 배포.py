# -*- coding: utf-8 -*-
"""
노트앱 배포 — 빌드하고 GitHub Pages 에 올린다.

  python 배포.py            빌드 → 커밋 → 푸시 → (처음이면 저장소·Pages 만들기) → 주소 출력
  python 배포.py --주소     지금 주소만 보여준다

처음 한 번은 GitHub 로그인이 필요하다. 이 스크립트가 `gh auth login` 을 띄우니
브라우저에서 코드를 입력하면 된다. 계정이 없으면 그 화면에서 Google 계정으로 만들 수 있다.
저장소는 공개(public) 로 만든다 — 무료 계정의 Pages 는 공개 저장소만 된다. 앱 코드뿐 사건 자료는 들어가지 않는다.
"""
import json, re, subprocess, sys, time, io
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent
REPO = "notedesk"
APPS = [("gijil", "기일노트", ROOT.parent / "기일노트" / "사용법.md"),
        ("josa", "조사노트", ROOT.parent / "조사노트" / "사용법.md"),
        ("sangdam", "상담노트", ROOT.parent / "상담노트" / "사용법.md")]

def sh(*args, check=True, capture=True, cwd=ROOT):
    r = subprocess.run(list(args), cwd=str(cwd), capture_output=capture, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise SystemExit(f"실패: {' '.join(args)}\n{(r.stderr or r.stdout or '').strip()}")
    return (r.stdout or "").strip()

def ensure_login():
    r = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode == 0: return
    print("GitHub 로그인이 필요합니다. 브라우저가 열리면 화면의 코드를 입력하세요. (계정이 없으면 Sign up → Continue with Google)")
    rc = subprocess.call(["gh", "auth", "login", "--web", "--hostname", "github.com", "--git-protocol", "https", "--scopes", "repo,workflow"])
    if rc != 0: raise SystemExit("로그인이 끝나지 않았습니다. 다시 실행하세요.")
    subprocess.call(["gh", "auth", "setup-git"])

def user_login():
    return sh("gh", "api", "user", "--jq", ".login")

def ensure_repo(user):
    if not (ROOT / ".git").exists():
        sh("git", "init", "-b", "main")
    ign = ROOT / ".gitignore"
    if not ign.exists(): ign.write_text("__pycache__/\n*.pyc\n.DS_Store\nThumbs.db\n", encoding="utf-8")
    sh("git", "add", "-A")
    if sh("git", "status", "--porcelain"):
        sh("git", "commit", "-q", "-m", "배포 " + time.strftime("%Y-%m-%d %H:%M"))
    remotes = sh("git", "remote")
    if "origin" not in remotes.split():
        exists = subprocess.run(["gh", "repo", "view", f"{user}/{REPO}"], capture_output=True).returncode == 0
        if exists:
            sh("git", "remote", "add", "origin", f"https://github.com/{user}/{REPO}.git")
        else:
            print(f"저장소 {user}/{REPO} 를 만듭니다 (public)")
            sh("gh", "repo", "create", REPO, "--public", "--source", ".", "--remote", "origin",
               "--description", "기일노트 · 조사노트 · 상담노트 — 변호사용 아이패드 노트앱")
    sh("git", "push", "-u", "origin", "main", capture=True)

def ensure_pages(user):
    r = subprocess.run(["gh", "api", f"repos/{user}/{REPO}/pages"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("GitHub Pages 를 켭니다 (main 브랜치 /docs)")
        sh("gh", "api", "-X", "POST", f"repos/{user}/{REPO}/pages", "-f", "build_type=legacy",
           "-f", "source[branch]=main", "-f", "source[path]=/docs")
    else:
        info = json.loads(r.stdout or "{}")
        src = info.get("source") or {}
        if src.get("branch") != "main" or src.get("path") != "/docs":
            sh("gh", "api", "-X", "PUT", f"repos/{user}/{REPO}/pages", "-f", "source[branch]=main", "-f", "source[path]=/docs")
    for _ in range(40):
        info = json.loads(sh("gh", "api", f"repos/{user}/{REPO}/pages") or "{}")
        if info.get("html_url"): return info["html_url"].rstrip("/") + "/"
        time.sleep(3)
    raise SystemExit("Pages 주소를 받지 못했습니다. 잠시 뒤 `python 배포.py --주소` 로 확인하세요.")

def wait_live(base):
    """첫 배포는 1~2분 걸린다. 사이트가 뜰 때까지 기다린다."""
    import urllib.request
    v = re.search(r'const V="([^"]+)"', (ROOT / "docs" / "sw.js").read_text(encoding="utf-8")).group(1)
    for i in range(60):
        try:
            with urllib.request.urlopen(base + "sw.js?" + str(time.time()), timeout=10) as r:
                if v in r.read().decode("utf-8", "replace"): return True
        except Exception:
            pass
        if i == 0: print("사이트가 뜨기를 기다립니다", end="", flush=True)
        print(".", end="", flush=True); time.sleep(5)
    print(); return False

def write_urls(base):
    lines = [f"# 노트앱 주소\n", f"- 첫 화면: {base}"]
    for d, name, doc in APPS:
        url = f"{base}{d}/"
        lines.append(f"- {name}: {url}")
        if doc.exists():
            s = doc.read_text(encoding="utf-8")
            s2 = re.sub(r"^앱 주소 — \S+", f"앱 주소 — {url}", s, count=1, flags=re.M)
            if s2 != s: doc.write_text(s2, encoding="utf-8")
    (ROOT / "주소.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

def main():
    if "--주소" in sys.argv:
        p = ROOT / "주소.md"
        print(p.read_text(encoding="utf-8") if p.exists() else "아직 배포한 적이 없습니다."); return
    sys.path.insert(0, str(ROOT))
    import importlib; build = importlib.import_module("빌드"); build.main()
    ensure_login()
    user = user_login()
    ensure_repo(user)
    base = ensure_pages(user)
    live = wait_live(base)
    print("\n배포 " + ("완료" if live else "푸시 완료 — 사이트 반영은 1~2분 더 걸릴 수 있습니다"))
    write_urls(base)
    print("\n아이패드 사파리에서 앱 주소를 열고 공유 → 「홈 화면에 추가」. 예전(claude.ai) 홈 화면 아이콘은 지워도 됩니다.")

if __name__ == "__main__":
    main()
