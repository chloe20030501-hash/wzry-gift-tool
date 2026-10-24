#!/usr/bin/env python3
"""打包「总包」—— 一份拿走的全家桶。

总包 = 给**人**看的总结 + 给**AI**看的交接手册 + 可执行的项目包 + 抓包指南。

生成:
    dist/王者送礼助手-总包-<日期>/          # 解压即用的文件夹
    dist/王者送礼助手-总包-<日期>.zip       # 同一份的压缩包(发给别人/存网盘)

内部结构:
    ① 先看这个-今天做了什么与下一步.md        人类版：进度、待办、指引
    ② AI交接手册-HANDOFF.md                 换模型/换工作台时让新 AI 读这一份
    ③ 抓包备用路线-操作清单.md              手机端一步一步
    ④ 项目完整包-wzry-gift-tool-<版本>.zip   源码+文档+抓包工具（干净副本）
    ⑤ 给AI的快速入口-AGENTS.md / CLAUDE.md
    ⑥ 版本历史-CHANGELOG.md
    总包说明.md                             这一包里有啥、先读哪本

⚠️ 默认**不含**个人数据(朋友档案)与任何凭据/私钥。
   想要连档案一起备份: python3 tools/pack_all.py --with-data

用法:
    python3 tools/pack_all.py               # 构建总包
    python3 tools/pack_all.py --with-data   # 额外把个人档案放进去(谨慎外发)
"""

import argparse
import datetime
import os
import shutil
import subprocess
import sys
import zipfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from gifttool import __version__  # noqa: E402

DIST_DIR = os.path.join(_ROOT, "dist")
PKG_NAME = "王者送礼助手-总包"

# (总包内的文件名, 项目内的相对路径) —— 文件不存在则跳过并告警
PICK = [
    ("① 先看这个-今天做了什么与下一步.md", "docs/今日总结与下一步.md"),
    ("② AI交接手册-HANDOFF.md", "HANDOFF.md"),
    ("③ 抓包备用路线-操作清单.md", "capture/抓包操作清单.md"),
    ("⑤ 给AI的快速入口-AGENTS.md", "AGENTS.md"),
    ("⑤ 给AI的快速入口-CLAUDE.md", "CLAUDE.md"),
    ("⑥ 版本历史-CHANGELOG.md", "CHANGELOG.md"),
    ("⑦ 项目说明-README.md", "README.md"),
    ("⑦ 界面截图-screenshot.png", "docs/screenshot.png"),
    ("⑧ 许可证-LICENSE", "LICENSE"),
]

# 个人数据(仅在 --with-data 时纳入)
PERSONAL = [
    ("data/friends.json", "friends.json"),
    ("data/onsale.json", "onsale.json"),
    ("data/skin_notes.json", "skin_notes.json"),
]

README_TMPL = """# 王者送礼助手 · 总包

打包时间：{when}  ·  项目版本：v{version}

这一包里有三样东西：**给你看的、给 AI 看的、能直接跑的**。

---

## 先读哪本？

| 顺序 | 文件 | 谁看 | 内容 |
|---|---|---|---|
| 1️⃣ | `① 先看这个-今天做了什么与下一步.md` | **你** | 今天做到哪了、明天做什么、怎么用。没术语，十几分钟看完 |
| 2️⃣ | `③ 抓包备用路线-操作清单.md` | **你** | 如果明天要接真实数据，照它做 |
| 3️⃣ | `② AI交接手册-HANDOFF.md` | **AI** | 换模型 / 换工作台时，让新 AI **先读完这一份**再动手 |

## 想直接跑起来

解压 `④ 项目完整包-wzry-gift-tool-{version}.zip`，然后：

```bash
cd wzry-gift-tool-{version}
python3 -m gifttool serve      # 然后浏览器打开 http://127.0.0.1:8765
```

零第三方依赖，只要有 Python 3.8+ 就能跑。

## 换 AI 的时候，第一句话这样说

> 「先读 `HANDOFF.md` 和 `docs/今日总结与下一步.md`，然后我们继续做 T1 抓包验证。」

新 AI 读完就接上了，你不用复述任何东西。

---

## ⚠️ 两件安全提醒

1. **本包不含你的朋友档案，也不含任何登录凭据。** 这是故意的。
   - 想要连档案一起备份，跑一次：`python3 tools/pack_all.py --with-data`
   - 没跑就是干净的，可以放心发给别人 / 传到 GitHub。
2. **项目文件夹里有几样东西千万别外发**（它们不在本包里，但在你的项目目录里）：
   - `ck.txt`（营地登录凭据，等于账号密码）
   - `capture/wireguard_手机配置.conf`（含 VPN 私钥）
   - `capture/证书发到手机/`（含中间人证书私钥）
   - `capture/hosts_*.log` / `conn_*.log`（含你的真实访问记录）

---

## 本包内容

{listing}

{data_section}
"""


def _stage_path():
    day = datetime.date.today().isoformat()
    return os.path.join(DIST_DIR, "%s-%s" % (PKG_NAME, day)), day


def build_release_zip():
    """调用 tools/pack.py 生成项目发布包,返回 zip 路径。"""
    print("=== 步骤 1/2：生成项目完整包 ===")
    r = subprocess.run(
        [sys.executable, os.path.join(_ROOT, "tools", "pack.py")],
        cwd=_ROOT,
    )
    if r.returncode != 0:
        print("!! 项目包构建或安检未通过,总包中止 !!")
        return None
    zip_path = os.path.join(DIST_DIR, "wzry-gift-tool-%s.zip" % __version__)
    if not os.path.exists(zip_path):
        print("!! 找不到 %s !!" % zip_path)
        return None
    return zip_path


def main():
    ap = argparse.ArgumentParser(description="打包总包")
    ap.add_argument("--with-data", action="store_true",
                    help="把个人档案也放进去(含真实好友数据,外发前请三思)")
    args = ap.parse_args()

    release = build_release_zip()
    if not release:
        return 1

    stage, day = _stage_path()
    if os.path.exists(stage):
        shutil.rmtree(stage)
    os.makedirs(stage, exist_ok=True)

    print()
    print("=== 步骤 2/2：组装总包 ===")
    listing = []
    for dst_name, rel in PICK:
        src = os.path.join(_ROOT, rel)
        if not os.path.exists(src):
            print("  ⚠️  跳过（不存在）: %s" % rel)
            continue
        dst = os.path.join(stage, dst_name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        print("  + %s" % dst_name)
        listing.append("| `%s` | %s |" % (dst_name, rel))

    # 项目包
    dst_zip = os.path.join(stage, "④ 项目完整包-wzry-gift-tool-%s.zip" % __version__)
    shutil.copy2(release, dst_zip)
    print("  + ④ 项目完整包-wzry-gift-tool-%s.zip" % __version__)
    listing.append("| `④ 项目完整包-wzry-gift-tool-%s.zip` | 源码 + 文档 + 抓包工具（%d KB） |"
                   % (__version__, os.path.getsize(dst_zip) // 1024))

    # 个人数据（可选）
    data_section = ""
    if args.with_data:
        ddir = os.path.join(stage, "⑨ 个人档案（含真实好友数据-外发前请删除）")
        os.makedirs(ddir, exist_ok=True)
        got = []
        for rel, name in PERSONAL:
            src = os.path.join(_ROOT, rel)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(ddir, name))
                got.append(name)
        print("  + ⑨ 个人档案/  (%s)" % ", ".join(got))
        data_section = (
            "## ⑨ 个人档案\n\n本包**包含**了你的个人档案（`%s`）。\n"
            "这里面有真实好友的营地 ID 与聊天备注 —— **发给任何人之前请先删掉这个文件夹**。\n"
            % "、".join(got)
        )
        listing.append("| `⑨ 个人档案（含真实好友数据-外发前请删除）/` | %s |" % "、".join(got))

    # 总包说明
    readme = README_TMPL.format(
        when=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        version=__version__,
        listing="\n".join(listing),
        data_section=data_section,
    )
    with open(os.path.join(stage, "总包说明.md"), "w", encoding="utf-8") as f:
        f.write(readme)
    print("  + 总包说明.md")

    zip_out = os.path.join(DIST_DIR, "%s-%s.zip" % (PKG_NAME, day))
    if os.path.exists(zip_out):
        os.remove(zip_out)
    with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, fs in os.walk(stage):
            for fn in sorted(fs):
                full = os.path.join(root, fn)
                arc = os.path.join(os.path.basename(stage), os.path.relpath(full, stage))
                z.write(full, arc)

    print()
    print("总包目录: %s" % stage)
    print("总包压缩: %s  (%.1f MB)" % (zip_out, os.path.getsize(zip_out) / 1024.0 / 1024.0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
