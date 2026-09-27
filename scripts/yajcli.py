"""Windows と macOS の両方で同じように動かすための共通処理。

各スクリプトから `import yajcli` して使う（scripts/ に置いてあるので、
`python scripts/xxx.py` と実行すればそのまま読み込める）。

Windows で気をつけること
  - Python の既定の文字コードが cp932 になる。ファイルは必ず encoding="utf-8" で読み書きする。
    子プロセスの Python にも PYTHONUTF8=1 を渡す（出力をパイプで受けるときに文字化けしないように）
  - Azure CLI は az.cmd。名前だけでは subprocess から呼べないので、shutil.which で実体の場所を引く
  - pac / az の出力は、コンソールのコード ページ（日本語 Windows では cp932）で来ることがある。
    UTF-8 で読めなければ cp932 で読み直す
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = os.name == "nt"

# 出力を UTF-8 にする。Windows で出力をパイプやファイルに流すと、既定では cp932 になり、
# ✓ ✗ ⚠ などの記号（cp932 に無い）で UnicodeEncodeError になる。
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and (getattr(_stream, "encoding", "") or "").lower().replace("-", "") != "utf8":
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def info(msg):
    print(f"==> {msg}", flush=True)


def warn(msg):
    print(f"[!] {msg}", file=sys.stderr, flush=True)


def die(msg, code=1):
    print(f"[x] {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


def which(name):
    """pac / az / pdftotext などの実行ファイルの場所。無ければ None。"""
    return shutil.which(name)


def child_env(extra=None):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if extra:
        env.update(extra)
    return env


def _decode(data):
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp932" if IS_WINDOWS else "utf-8", errors="replace")


def run(cmd, check=False, capture=True, timeout=None, env=None):
    """外部コマンドを実行する。cmd[0] は名前でよい（which で解決する）。

    capture=True なら (終了コード, 出力) を返す。capture=False なら画面にそのまま出す。
    """
    exe = which(cmd[0]) or cmd[0]
    try:
        p = subprocess.run([exe, *cmd[1:]], capture_output=capture, timeout=timeout,
                           env=child_env(env))
    except FileNotFoundError:
        if check:
            die(f"{cmd[0]} が見つかりません")
        return 127, f"{cmd[0]} が見つかりません"
    except subprocess.TimeoutExpired:
        if check:
            die(f"{cmd[0]} が {timeout} 秒以内に終わりませんでした")
        return 124, f"{cmd[0]} が時間内に終わりませんでした"
    out = (_decode(p.stdout) + _decode(p.stderr)) if capture else ""
    if check and p.returncode != 0:
        die(f"{' '.join(cmd[:3])} が失敗しました（終了コード {p.returncode}）\n{out[-2000:]}")
    return p.returncode, out


def python(script, *args, check=True, capture=False, env=None):
    """scripts/ の Python スクリプトを、同じ Python（UTF-8 モード）で実行する。"""
    cmd = [sys.executable, "-X", "utf8", str(ROOT / "scripts" / script), *map(str, args)]
    try:
        p = subprocess.run(cmd, capture_output=capture, env=child_env(env), cwd=ROOT)
    except FileNotFoundError:
        die(f"{script} を実行できません")
    out = (_decode(p.stdout) + _decode(p.stderr)) if capture else ""
    if check and p.returncode != 0:
        if capture:
            print(out, end="")
        die(f"{script} が失敗しました（終了コード {p.returncode}）", p.returncode)
    return p.returncode, out


def az_token(resource):
    """Azure CLI のアクセストークン。サインインしていなければ None。"""
    code, out = run(["az", "account", "get-access-token", "--resource", resource,
                     "--query", "accessToken", "-o", "tsv"])
    tok = out.strip().splitlines()[-1].strip() if code == 0 and out.strip() else ""
    return tok if tok and " " not in tok else None


def load_config():
    path = Path(os.environ.get("YAJ_CONFIG", ROOT / "solution/config.json"))
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        die(f"設定ファイルがありません: {path}")
    return path, json.loads(path.read_text(encoding="utf-8"))


def check_pac_profile():
    """有効な pac プロファイルが YAJ_PAC_PROFILE（既定 yanmar-test）であることを確かめる。

    同じ PC に別案件（別テナント）のプロファイルがあると、たまたま有効だったものに
    向けてデプロイしてしまう。名前付きのプロファイルを明示させる。
    """
    profile = os.environ.get("YAJ_PAC_PROFILE", "yanmar-test")
    info(f"認証プロファイルを確認します（想定: {profile}）")
    if not which("pac"):
        die("pac が見つかりません。docs/11-production-deployment.md の 2-1 でインストールしてください")
    code, out = run(["pac", "auth", "list"])
    active = next((l for l in out.splitlines() if len(l.split()) > 3 and l.split()[1] == "*"), "")
    name = active.split()[3] if active else ""
    if not name:
        die(f"有効な認証プロファイルがありません。次を実行してください:\n    pac auth create --name {profile}")
    if name != profile:
        die(f"有効なプロファイルが '{name}' です。想定は '{profile}' です。\n"
            f"  別案件のテナントにデプロイする事故を防ぐため中止します。切り替えるには:\n"
            f"    pac auth select --name {profile}\n"
            f"  （別名のプロファイルを使う場合は環境変数 YAJ_PAC_PROFILE に名前を入れる）")
    print("    " + " ".join(active.split()[3:5]), flush=True)
    return profile


def dataverse(env, token):
    """Dataverse Web API を呼ぶ関数を返す: call(method, path, body=None) -> (status, json)。"""
    import urllib.error
    import urllib.parse
    import urllib.request

    base = env.rstrip("/") + "/api/data/v9.2/"

    def call(method, path, body=None):
        url = base + urllib.parse.quote(path, safe="/?&=$,()'")
        req = urllib.request.Request(
            url, method=method, data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raw = e.read() or b"{}"
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, {"raw": raw[:300].decode(errors="replace")}

    return call


def import_solution(env, zip_path, solution_name, extra_args=(), timeout=900):
    """pac solution import を実行する。pac が戻らないときはインポートジョブの結果で判定する。

    テスト用テナントで、インポート自体は数十秒で終わっているのに pac が応答待ちのまま
    10分以上戻らないことが2回あった（2026-09-28）。timeout 秒で pac を打ち切り、
    Dataverse のインポートジョブ（importjobs）が完了していれば成功とみなす。
    """
    import time

    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60))
    cmd = [which("pac") or "pac", "solution", "import", "--environment", env, "--path", str(zip_path),
           *extra_args, "--max-async-wait-time", "30"]
    try:
        p = subprocess.run(cmd, env=child_env(), timeout=timeout)
        return p.returncode == 0
    except subprocess.TimeoutExpired:
        warn(f"pac が {timeout} 秒たっても戻らないため打ち切り、インポートジョブの結果を確かめます")
    token = az_token(env)
    if not token:
        warn("Azure CLI にサインインしていないため、ジョブの結果を確かめられません")
        return False
    call = dataverse(env, token)
    job = None
    for _ in range(30):   # 最大5分、ジョブの完了を待つ
        st, jobs = call("GET", f"importjobs?$select=solutionname,progress,completedon,createdon"
                               f"&$filter=solutionname eq '{solution_name}' and createdon ge {started}"
                               f"&$orderby=createdon desc&$top=1")
        job = (jobs.get("value") or [None])[0]
        if job and job.get("completedon"):
            if float(job.get("progress") or 0) >= 100:
                info(f"インポートジョブは完了しています（{job['createdon']} 開始、{job['completedon']} 完了）")
                return True
            break
        time.sleep(10)
    warn(f"インポートジョブが完了していません: {job}")
    return False
