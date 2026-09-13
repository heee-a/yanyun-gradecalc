"""通过 GitHub API 推送本地提交（github.com 直连被阻断时的替代路径）。

- 远端为空仓库：Contents API 建初始提交 + Git Data API 推全部文件；
- 远端非空：以远端 HEAD 为父提交，增量推送 origin/main..HEAD 的变更文件。

用法: TOKEN=xxx python api_push.py <owner/name>
"""

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = sys.argv[1]
TOKEN = os.environ["TOKEN"]
API = f"https://api.github.com/repos/{REPO}"


def api(method: str, path: str, payload: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={
            "Authorization": f"token {TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "api-push-script",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return json.loads(body) if body else {}


def blob_tree_entries(paths: list[str]) -> list[dict]:
    entries = []
    for path in paths:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        blob = api("POST", "/git/blobs", {"content": b64, "encoding": "base64"})
        entries.append({"path": path.replace("\\", "/"), "mode": "100644",
                        "type": "blob", "sha": blob["sha"]})
    return entries


def tracked_files() -> list[str]:
    files = subprocess.check_output(
        ["git", "-c", "core.quotepath=false", "ls-files"],
        text=True, encoding="utf-8").splitlines()
    return [f.strip() for f in files if f.strip()]


def changed_files() -> list[str]:
    files = subprocess.check_output(
        ["git", "-c", "core.quotepath=false", "diff", "--name-only",
         "origin/main", "HEAD"], text=True, encoding="utf-8").splitlines()
    return [p.strip('"').strip() for p in files if p.strip()]


def main() -> None:
    readme = "README.md"
    files = tracked_files()
    assert readme in files, "README.md 必须存在（初始化提交的种子文件）"

    # 判断远端是否为空仓库
    empty = False
    try:
        head = api("GET", "/git/refs/heads/main")["object"]["sha"]
        print(f"远端 HEAD {head[:10]} -> 增量模式")
    except urllib.error.HTTPError as e:
        if e.code != 409:
            raise
        empty = True
        print("远端为空仓库 -> 初始化模式")

    if empty:
        with open(readme, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        try:
            api("PUT", f"/contents/{readme}",
                {"message": "init", "content": b64, "branch": "main"})
        except urllib.error.HTTPError as e:
            if e.code != 422:
                raise
        head = None
        for _ in range(6):  # 初始提交的 ref 有最终一致性延迟
            try:
                head = api("GET", "/git/refs/heads/main")["object"]["sha"]
                break
            except urllib.error.HTTPError as e:
                if e.code != 409:
                    raise
                time.sleep(3)
        if head is None:
            raise RuntimeError("远端 refs/heads/main 始终不可见")
        print(f"初始提交 {head[:10]}")

    # 全量树模式：不做本地 diff（远端提交对象不在本地对象库），
    # 直接以全部跟踪文件重建完整树，父提交指向远端 HEAD。
    files = tracked_files()

    tree_entries = blob_tree_entries(files)
    print(f"上传 blob {len(tree_entries)} 个")
    tree = api("POST", "/git/trees", {"tree": tree_entries})
    msg = subprocess.check_output(
        ["git", "-c", "core.quotepath=false", "log", "-1", "--pretty=%B", "HEAD"],
        text=True, encoding="utf-8")
    commit = api("POST", "/git/commits",
                 {"message": msg, "tree": tree["sha"], "parents": [head]})
    api("PATCH", "/git/refs/heads/main", {"sha": commit["sha"], "force": False})
    print(f"main -> {commit['sha'][:10]}")
    print("API 推送完成")


if __name__ == "__main__":
    main()
