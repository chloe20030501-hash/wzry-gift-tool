#!/usr/bin/env python3
"""从官方英雄列表接口生成静态名册 data/heroes.json。

名册用途:
  1. 备注解析 —— 从「他最近爱玩公孙离」这类自由文本里识别英雄;
  2. 皮肤名校验 —— 判断备注里提到的皮肤是不是真皮肤。

用法:
  python3 tools/build_heroes.py            # 联网更新
  python3 tools/build_heroes.py --offline  # 用本地缓存 herolist.json
"""

import argparse
import datetime
import json
import os
import urllib.request

SRC = "https://pvp.qq.com/web201605/js/herolist.json"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "heroes.json")
CACHE = os.path.join(ROOT, "data", "herolist.raw.json")

# 常见俗称/黑话 -> 正式英雄名。备注里出现俗称也能识别。
ALIASES = {
    # 俗称/黑话 -> 正式英雄名
    "猴子": "孙悟空", "大圣": "孙悟空", "悟空": "孙悟空",
    "大小姐": "孙尚香", "香香": "孙尚香",
    "草丛伦": "亚瑟", "鲁班": "鲁班七号", "小鲁班": "鲁班七号",
    "奶妈": "蔡文姬", "文姬": "蔡文姬", "鱼": "庄周",
    "老亚瑟": "亚瑟", "貂蝉妹妹": "貂蝉", "铠爹": "铠", "峡谷之光": "亚瑟",
}
# 位置/职业词:出现在备注里不算英雄,显式排除
NOT_HERO_WORDS = [
    "射手", "辅助", "打野", "中单", "上单", "对抗路", "发育路", "游走",
    "法师", "刺客", "坦克", "战士", "队友", "对面",
]


def fetch():
    req = urllib.request.Request(SRC, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build(raw):
    heroes = []
    for h in raw:
        name = (h.get("cname") or "").strip()
        if not name:
            continue
        skins = [s.strip() for s in (h.get("skin_name") or "").split("|") if s.strip()]
        heroes.append({
            "id": int(h["ename"]),
            "name": name,
            "title": (h.get("title") or "").strip(),
            "skins": skins,
        })
    heroes.sort(key=lambda x: x["id"])
    valid = {h["name"] for h in heroes}
    aliases = {k: v for k, v in ALIASES.items() if v in valid}
    return {
        "source": SRC,
        "fetched_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "count": len(heroes),
        "heroes": heroes,
        "aliases": aliases,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="使用本地缓存")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if args.offline and os.path.exists(CACHE):
        raw = json.load(open(CACHE, encoding="utf-8"))
    else:
        raw = fetch()
        json.dump(raw, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

    data = build(raw)
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    skin_total = sum(len(h["skins"]) for h in data["heroes"])
    print("已生成 %s" % OUT)
    print("英雄 %d 个 · 皮肤名 %d 个 · 俗称 %d 条"
          % (data["count"], skin_total, len(data["aliases"])))


if __name__ == "__main__":
    main()
