#!/usr/bin/env python3
"""打包发布包。

生成 dist/wzry-gift-tool-<version>.zip 与 .tar.gz,内容为一份**干净的**项目副本:

  - 保留全部源码、文档、打包脚本、抓包脚本、以及官方英雄名册(data/heroes.json)
  - 排除个人数据: data/friends.json / onsale.json / skin_notes.json 恢复成空模板
  - 排除抓包留档 dumps/ 与报告 output/ 里的内容(只留空目录)
  - 排除 **capture/ 下的所有运行产物**: 侦察日志(*.log)、流量留档(flows.mitm)、
    原始响应 dump、WireGuard 客户端配置(*.conf,含私钥)、给手机用的 CA 证书(含私钥)
  - 排除 ck.txt / ck_source.txt(账号凭据)、__pycache__、dist、.tmp、.git

打包结束会**自动安检**: 扫描压缩包内是否有可疑文件(凭据/私钥/日志/系统文件),
有就打印告警并以非 0 退出(见 `_safety_scan`)。

用法:
    python3 tools/pack.py              # 打包
    python3 tools/pack.py --list       # 只看会包含哪些文件
    python3 tools/pack.py --portfolio  # 公开展示版(去掉抓包工具与内部文档)
"""

import argparse
import fnmatch
import os
import shutil
import sys
import tarfile
import zipfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from gifttool import __version__  # noqa: E402

PROJECT_NAME = "wzry-gift-tool"
DIST_DIR = os.path.join(_ROOT, "dist")

# 整目录排除（按目录名匹配）
EXCLUDE_DIRS = {
    ".git", ".github", "__pycache__", ".pytest_cache", ".idea", ".vscode",
    ".tmp", "dist", "venv", ".venv", "node_modules",
    "dumps", "output",                 # 含真实玩家数据,只保留空目录占位
}

# 排除但需要"空目录占位"的目录
PLACEHOLDER_DIRS = ["dumps", "output"]

# 单文件排除（按"相对路径"精确匹配）
EXCLUDE_FILES = {
    "ck.txt", "ck", "ck_source.txt", ".DS_Store",
    "data/friends.json",               # 个人档案 → 换成 friends.example.json
}

# 通配符排除（按"相对路径"逐段匹配, 用 fnmatch 语义）。
# ⚠️ 这一组是安全底线: 抓包目录里的日志/流量/私钥/证书**绝不能进发布包**。
EXCLUDE_GLOBS = {
    "capture/*.log",                   # hosts / conn / headers 侦察日志(含真实玩家数据)
    "capture/hosts_*.log",
    "capture/conn_*.log",
    "capture/flows.mitm",              # 完整流量留档
    "capture/*.conf",                  # WireGuard 客户端配置(含私钥)
    "capture/*.cer", "capture/*.pem", "capture/*.key", "capture/*.crt",
    "capture/dump/*",                  # 原始响应 dump
    "capture/证书发到手机/*",           # mitmproxy CA 证书拷贝(同目录含私钥)
    "*.pyc", "*.pyo", "*.swp", "*.log", "*~", "*.DS_Store",
}

# 打包时内容被重置为"空模板"的文件(避免把个人名单带出去)
RESET_FILES = {
    "data/onsale.json": "[]\n",
    "data/skin_notes.json": "{}\n",
}

# 公开展示版(--portfolio)额外排除: 抓包工具与内部文档
# 理由: ① 合规 —— 不公开分发"抓取第三方 App 凭据"的工具与指引;
#       ② 隐私 —— HANDOFF/今日总结里有本机路径、个人偏好等工作笔记。
PORTFOLIO_EXCLUDE_GLOBS = {
    "capture/*",
    "HANDOFF.md", "AGENTS.md", "CLAUDE.md",
    "docs/今日总结与下一步.md",
    "docs/项目梳理-求职版.md",
}

PORTFOLIO = False

# 安检规则: 压缩包里出现这些就告警
_SUSPICIOUS_GLOBS = [
    "*/ck.txt", "*/ck_source.txt", "*.conf", "*.log", "*.mitm",
    "*.cer", "*.pem", "*.key", "*.crt", "*证书发到手机*", "*.DS_Store",
    "*/friends.json",
]


def _excluded(posix_rel):
    """相对路径(用 / 分隔)是否应排除。

    注意: Python 的 fnmatch 里 `*` 也匹配 `/`, 所以 `capture/*.log`
    能同时命中 `capture/a.log` 与 `capture/sub/a.log` —— 这正是我们要的。
    """
    if posix_rel in EXCLUDE_FILES:
        return True
    if PORTFOLIO and any(fnmatch.fnmatch(posix_rel, pat)
                         for pat in PORTFOLIO_EXCLUDE_GLOBS):
        return True
    return any(fnmatch.fnmatch(posix_rel, pat) for pat in EXCLUDE_GLOBS)


def _rel_files():
    """遍历项目,产出应打包的相对路径。"""
    out = []
    for root, dirs, files in os.walk(_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for fn in sorted(files):
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, _ROOT)
            posix = rel.replace(os.sep, "/")
            if _excluded(posix):
                continue
            out.append(rel)
    return sorted(out)


def _safety_scan(archive_path):
    """扫描已生成的压缩包。

    返回 (可疑成员列表, 已确认安全的例外列表)。
    注意: `data/friends.json` 会被命中, 但那通常是打包时自动放入的**空模板** ——
    所以这里要看**内容**是否与 `data/friends.example.json` 完全一致, 一致才算安全。
    """
    ex_path = os.path.join(_ROOT, "data", "friends.example.json")
    example = None
    if os.path.exists(ex_path):
        with open(ex_path, "r", encoding="utf-8") as f:
            example = f.read()

    zf = None
    tf = None
    if archive_path.endswith(".zip"):
        zf = zipfile.ZipFile(archive_path)
        names = zf.namelist()

        def _read(name):
            return zf.read(name).decode("utf-8", "ignore")
    else:
        tf = tarfile.open(archive_path)
        names = tf.getnames()

        def _read(name):
            fh = tf.extractfile(name)
            return fh.read().decode("utf-8", "ignore") if fh else ""

    hits, safe = [], []
    try:
        for name in names:
            base = name.rsplit("/", 1)[-1]
            if base == "friends.json" and example is not None:
                try:
                    if _read(name) == example:
                        safe.append(name)
                        continue
                except Exception:
                    pass
            for pat in _SUSPICIOUS_GLOBS:
                if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(name, "*/" + pat):
                    hits.append(name)
                    break
    finally:
        if zf is not None:
            zf.close()
        if tf is not None:
            tf.close()
    return sorted(set(hits)), sorted(set(safe))


def _write_tree(dest):
    """把干净副本写到 dest 目录(项目根)。返回文件数。"""
    n = 0
    for rel in _rel_files():
        src = os.path.join(_ROOT, rel)
        dst = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        posix = rel.replace(os.sep, "/")
        if posix in RESET_FILES:
            with open(dst, "w", encoding="utf-8") as f:
                f.write(RESET_FILES[posix])
        else:
            shutil.copy2(src, dst)
        n += 1

    # 空目录占位,并放 .gitkeep 让 git 也能保留结构
    for d in PLACEHOLDER_DIRS:
        p = os.path.join(dest, d)
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, ".gitkeep"), "w", encoding="utf-8") as f:
            f.write("")
        n += 1

    # 若没有 friends.json,放一份空模板,保证克隆下来就能跑
    fj = os.path.join(dest, "data", "friends.json")
    if not os.path.exists(fj):
        shutil.copy2(os.path.join(dest, "data", "friends.example.json"), fj)
        n += 1
    return n


def main():
    global PORTFOLIO
    ap = argparse.ArgumentParser(description="打包发布包")
    ap.add_argument("--list", action="store_true", help="只列出会包含的文件")
    ap.add_argument("--portfolio", action="store_true",
                    help="公开展示版：不含抓包工具与内部文档")
    args = ap.parse_args()
    PORTFOLIO = args.portfolio

    files = _rel_files()
    if args.list:
        for f in files:
            print(f)
        print("--- 共 %d 个文件%s" % (len(files), "（公开展示版）" if PORTFOLIO else ""))
        return 0

    base = "%s-%s%s" % (PROJECT_NAME, __version__, "-portfolio" if PORTFOLIO else "")
    stage = os.path.join(DIST_DIR, "_stage", base)
    if os.path.exists(os.path.join(DIST_DIR, "_stage")):
        shutil.rmtree(os.path.join(DIST_DIR, "_stage"))
    os.makedirs(stage, exist_ok=True)

    n = _write_tree(stage)
    print("已组装干净副本: %d 个文件" % n)

    os.makedirs(DIST_DIR, exist_ok=True)
    zip_path = os.path.join(DIST_DIR, base + ".zip")
    tgz_path = os.path.join(DIST_DIR, base + ".tar.gz")

    # zip
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, fs in os.walk(stage):
            for fn in sorted(fs):
                full = os.path.join(root, fn)
                arc = os.path.join(base, os.path.relpath(full, stage))
                z.write(full, arc)

    # tar.gz
    with tarfile.open(tgz_path, "w:gz") as t:
        t.add(stage, arcname=base)

    shutil.rmtree(os.path.join(DIST_DIR, "_stage"))

    for p in (zip_path, tgz_path):
        print("  %-44s %6.1f KB" % (os.path.basename(p), os.path.getsize(p) / 1024.0))

    print()
    bad = []
    allowed = []
    for p in (zip_path, tgz_path):
        hits, safe = _safety_scan(p)
        allowed.extend(safe)
        if hits:
            bad.append((p, hits))

    if bad:
        print("!! 安检不通过: 压缩包里出现了不应发布的文件 !!")
        for p, hits in bad:
            print("  [%s]" % os.path.basename(p))
            for h in hits[:20]:
                print("    -", h)
            if len(hits) > 20:
                print("    ... 另有 %d 个" % (len(hits) - 20))
        return 1

    print("安检通过: 未发现凭据 / 私钥 / 日志 / 个人数据。")
    if allowed:
        print("  （已核对内容、确认是空模板: %s）"
              % ", ".join(sorted({a.rsplit("/", 1)[-1] for a in allowed})))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
