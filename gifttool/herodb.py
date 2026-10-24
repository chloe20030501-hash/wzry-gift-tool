"""英雄名册与备注文本解析。

职责:
  1. 加载 data/heroes.json(英雄ID、名字、俗称、皮肤名);
  2. 从自由文本里识别英雄 / 「英雄·皮肤名」。

解析策略(重要,决定备注识别准不准):
  * 字典按长度降序贪心匹配,已命中的字符区间会被"遮罩",
    避免「鲁班七号」被拆成「鲁班」、「李白·凤求凰」被拆成两个英雄名;
  * 先扫皮肤名(更长更具体),再扫英雄名和俗称;
  * 单字英雄名(瑶/铠/曜/镜/弈)极易误命中(琼「瑶」、眼「镜」、星「曜」),
    所以只在命中情感词上下文时才认。
"""

import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEROES_FILE = os.path.join(_ROOT, "data", "heroes.json")

# 单字英雄名出现时,附近出现这些词才认(否则"眼镜""琼瑶""对弈"会误命中)
CONTEXT_WORDS = [
    "喜欢", "爱玩", "爱", "玩", "本命", "擅长", "常用", "主玩", "常玩",
    "英雄", "皮肤", "想要", "想要", "送", "中意", "迷", "练", "打",
    "缺", "买", "抽", "换",
]
CONTEXT_WINDOW = 8

# 备注里常见的情感/关系词,用于生成"理由"文案
REASON_WORDS = [
    ("本命", "他自称本命英雄"),
    ("最爱", "他提到最爱这个"),
    ("喜欢", "聊天里提到喜欢"),
    ("想要", "明确说过想要"),
    ("缺", "自己说缺这个"),
    ("经常玩", "经常玩"),
    ("主玩", "主玩"),
]


class HeroDB:
    def __init__(self, data):
        self.heroes = data.get("heroes") or []
        self.aliases = data.get("aliases") or {}
        self.by_id = {h["id"]: h for h in self.heroes}
        self.by_name = {h["name"]: h for h in self.heroes}
        # 皮肤名 -> 英雄;同名皮肤极少,重复时保留第一个
        self.skin_owner = {}
        for h in self.heroes:
            for s in h["skins"]:
                self.skin_owner.setdefault(s, h)
        self._single_char = {h["name"] for h in self.heroes if len(h["name"]) == 1}

    def hero_id(self, name):
        h = self.by_name.get(name)
        return h["id"] if h else None

    def hero_name(self, hero_id):
        h = self.by_id.get(int(hero_id)) if hero_id is not None else None
        return h["name"] if h else ""

    def skins_of(self, hero_id):
        h = self.by_id.get(int(hero_id)) if hero_id is not None else None
        return list(h["skins"]) if h else []


def load(path=None):
    path = path or HEROES_FILE
    if not os.path.exists(path):
        return HeroDB({})
    with open(path, "r", encoding="utf-8") as f:
        return HeroDB(json.load(f))


def _scan_long(text, entries, claimed):
    """按长度降序贪心匹配 entries(元素为 (词, payload)),返回命中列表。

    claimed 是已占用区间列表 [(start, end)],防止重叠误命中。
    """
    hits = []
    for word, payload in entries:
        start = 0
        while True:
            idx = text.find(word, start)
            if idx < 0:
                break
            end = idx + len(word)
            if not any(idx < c_end and end > c_start for c_start, c_end in claimed):
                claimed.append((idx, end))
                hits.append({
                    "word": word, "start": idx, "end": end, "payload": payload,
                    "context": text[max(0, idx - 12):min(len(text), end + 12)],
                })
            start = idx + 1
    hits.sort(key=lambda x: x["start"])
    return hits


def _reason_for(context):
    for kw, desc in REASON_WORDS:
        if kw in context:
            return desc
    return "备注中提到"


def _narrow(text, start, end, span=6):
    """取命中词前后的窄窗口,用于判断情感理由(避免串到隔壁短语)。"""
    return text[max(0, start - span):min(len(text), end + span)]


def scan(text, db=None):
    """从文本里抽取英雄与皮肤。

    返回 {"heroes": [ {heroId,name,word,reason,context} ],
          "skins":  [ {heroId,hero,skin,reason,context} ]}
    """
    db = db or load()
    text = (text or "").strip()
    if not text:
        return {"heroes": [], "skins": []}

    claimed = []

    # 1. 皮肤名(最长,优先占位)
    skin_entries = sorted(db.skin_owner.items(), key=lambda kv: -len(kv[0]))
    skin_hits = _scan_long(text, skin_entries, claimed)

    # 2. 英雄名 + 俗称(长度>=2)
    name_entries = []
    for h in db.heroes:
        if len(h["name"]) >= 2:
            name_entries.append((h["name"], ("hero", h)))
    for alias, real in db.aliases.items():
        if len(alias) >= 2 and real in db.by_name:
            name_entries.append((alias, ("alias", db.by_name[real])))
    name_entries.sort(key=lambda kv: -len(kv[0]))
    name_hits = _scan_long(text, name_entries, claimed)

    # 3. 单字英雄名(仅在情感词上下文里认)
    single_entries = sorted(
        [(n, ("hero", db.by_name[n])) for n in db._single_char],
        key=lambda kv: -len(kv[0]),
    )
    single_hits = []
    for word, payload in single_entries:
        start = 0
        while True:
            idx = text.find(word, start)
            if idx < 0:
                break
            end = idx + len(word)
            window = text[max(0, idx - CONTEXT_WINDOW):min(len(text), end + CONTEXT_WINDOW)]
            overlap = any(idx < c_end and end > c_start for c_start, c_end in claimed)
            if not overlap and any(kw in window for kw in CONTEXT_WORDS):
                claimed.append((idx, end))
                single_hits.append({
                    "word": word, "start": idx, "end": end, "payload": payload,
                    "context": window,
                })
            start = idx + 1
    single_hits.sort(key=lambda x: x["start"])

    heroes, seen = [], set()
    for hit in sorted(name_hits + single_hits, key=lambda x: x["start"]):
        kind, h = hit["payload"]
        if h["id"] in seen:
            continue
        seen.add(h["id"])
        heroes.append({
            "heroId": h["id"], "name": h["name"], "word": hit["word"],
            "viaAlias": kind == "alias",
            "reason": _reason_for(_narrow(text, hit["start"], hit["end"])),
            "context": hit["context"].replace("\n", " ").strip(),
        })

    skins = []
    seen_skin = set()
    for hit in skin_hits:
        h = hit["payload"]
        key = (h["id"], hit["word"])
        if key in seen_skin:
            continue
        seen_skin.add(key)
        skins.append({
            "heroId": h["id"], "hero": h["name"], "skin": hit["word"],
            "reason": _reason_for(_narrow(text, hit["start"], hit["end"])),
            "context": hit["context"].replace("\n", " ").strip(),
        })
    return {"heroes": heroes, "skins": skins}


def find_skin(name, db=None):
    """把「祈雪灵祝」或「公孙离·祈雪灵祝」解析成 (heroId, hero, skin)。找不到返回 None。"""
    db = db or load()
    name = (name or "").strip()
    if not name:
        return None
    if "·" in name:
        hero_part, skin_part = name.split("·", 1)
        h = db.by_name.get(hero_part.strip())
        if h and (not skin_part or skin_part.strip() in h["skins"]):
            return (h["id"], h["name"], skin_part.strip() or h["skins"][0] if h["skins"] else skin_part.strip())
    h = db.skin_owner.get(name)
    if h:
        return (h["id"], h["name"], name)
    # 皮肤名带前缀/后缀(如"李白 凤求凰")
    for hero_name, h in db.by_name.items():
        for s in h["skins"]:
            if s and (s in name or name in s):
                return (h["id"], hero_name, s)
    return None
