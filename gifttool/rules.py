"""皮肤可赠送判定规则库(四态模型)。

限定皮肤有生命周期: 首售 -> 直售返场 -> 抽奖返场 -> 绝版。
只有落在「商城在售窗口内」的皮肤才能赠送,所以判定结果分四态:

  可赠送      当前商城在售(直售/正在直售返场的限定) -> 现在就能送
  返场时可送  限定/限时皮肤,曾经或可能以直售形式返场 -> 要等窗口,窗口内可送
  不可赠送    荣耀典藏、战令及其返场宝箱、抽奖返场、赛季/活动绝版、碎片兑换、星元
  待确认      规则说不准,以游戏内详情页「赠送」按钮为准

判定优先级:
  1. 你的人工标注(data/skin_notes.json,在管理页面点一下就写入,最优先)
  2. SKIN_NOTES 皮肤级标注(rules.py 内置,按「英雄·皮肤名」索引)
  3. 在售名单(onsale 集合,当前商城在售/正在返场的皮肤)
  4. 永久不可赠送关键词
  5. 限定/限时类关键词 -> 返场时可送
  6. 有点券价格 -> 视为常驻直售 -> 可赠送
"""

import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_NOTES_FILE = os.path.join(_ROOT, "data", "skin_notes.json")

# 四态
GIFTABLE = "可赠送"
ON_RETURN = "返场时可送"
NOT_GIFTABLE = "不可赠送"
UNKNOWN = "待确认"

# ---------------------------------------------------------------
# 皮肤级标注: 键为「英雄·皮肤名」(也可只用皮肤名)。
# 用在你已知确切获取方式、且关键词规则判不准的皮肤上。
# 字段: gift(四态之一) / rarity(品质覆盖,可选) / reason(说明)
# ---------------------------------------------------------------
SKIN_NOTES = {
    "李白·凤求凰": {
        "gift": NOT_GIFTABLE, "rarity": "传说",
        "reason": "鸡年限定2017年上线,最后一次直售返场为2020年1月,后续仅抽奖形式返场",
    },
    "小乔·纯白花嫁": {
        "gift": NOT_GIFTABLE, "rarity": "史诗",
        "reason": "情人节限定2016年上线,最后一次直售返场为2017年5月,后续仅红宝石抽奖返场",
    },
    "貂蝉·幻阙歌": {
        "gift": NOT_GIFTABLE, "rarity": "荣耀典藏",
        "reason": "荣耀典藏,荣耀水晶兑换,绑定账号无法赠送",
    },
    "貂蝉·遇见胡旋": {
        "gift": ON_RETURN, "rarity": "传说",
        "reason": "敦煌研究院联动限定,限时售卖,需等返场窗口",
    },
    "貂蝉·猫影幻舞": {
        "gift": ON_RETURN, "rarity": "传说",
        "reason": "FMVP 限定,限时售卖,需等返场窗口",
    },
}

# 命中即判「不可赠送」(永久性,不因返场而可送)
HARD_NO_KEYWORDS = [
    "荣耀典藏", "典藏", "夺宝", "荣耀水晶", "水晶兑换",
    "战令", "抽奖", "红宝石", "碎片兑换", "碎片商店",
    "赛季皮肤", "赛季限定", "活动免费", "免费领取", "累计充值",
    "星元", "紫星币", "星传说", "星史诗", "赛事战令",
]

# 命中判「返场时可送」(限定/限时类,等直售返场窗口才能送)
ON_RETURN_KEYWORDS = [
    "限定", "限时", "返场", "联动", "FMVP", "KPL", "世冠", "无双", "珍品",
    "情人节", "周年", "春节", "元宵", "五五", "敦煌", "鸡年", "狗年", "猪年",
    "鼠年", "牛年", "虎年", "兔年", "龙年", "蛇年", "马年", "内测",
]

# 命中标记「待确认」(不同来源规则冲突,以游戏内为准)
UNKNOWN_KEYWORDS = [
    "返场投票", "自选返场", "票选",
]

# 品质等级映射(营地 szClass -> 中文)
RARITY_MAP = {
    "SR": "荣耀典藏",
    "S++": "传说",
    "S+": "史诗",
    "S": "勇者",
    "A": "勇者",
    "B": "勇者",
    "C": "勇者",
    "D": "普通",
}

VERDICT_ORDER = {GIFTABLE: 0, ON_RETURN: 1, UNKNOWN: 2, NOT_GIFTABLE: 3}
RARITY_ORDER = {"荣耀典藏": 0, "传说": 1, "史诗": 2, "勇者": 3, "普通": 4, "未知": 5}


# ---------------------------------------------------------------
# 你的人工标注(data/skin_notes.json)
# 在管理页面点一下状态按钮就写进这个文件,优先级高于一切自动判定。
# 结构: {"英雄·皮肤名": {"gift": "不可赠送", "reason": "我自己核实过"}}
# ---------------------------------------------------------------
_notes_cache = {"mtime": None, "data": {}}


def user_notes(path=None):
    path = path or USER_NOTES_FILE
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    if _notes_cache["mtime"] != mtime:
        try:
            with open(path, "r", encoding="utf-8") as f:
                _notes_cache["data"] = json.load(f)
        except (ValueError, OSError):
            _notes_cache["data"] = {}
        _notes_cache["mtime"] = mtime
    return _notes_cache["data"]


def invalidate_cache():
    _notes_cache["mtime"] = None


def set_user_note(key, verdict, reason="", rarity=None):
    """写入一条人工标注。key 形如「貂蝉·幻阙歌」。"""
    path = USER_NOTES_FILE
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (ValueError, OSError):
            data = {}
    if verdict:
        entry = {"gift": verdict, "reason": reason or "你的人工标注"}
        if rarity:
            entry["rarity"] = rarity
        data[key] = entry
    else:
        data.pop(key, None)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    invalidate_cache()
    return data


def _lookup(notes, full_key, name):
    """在标注字典里查,先精确键再退化为只按皮肤名匹配。"""
    if not notes:
        return None
    if full_key and full_key in notes:
        return notes[full_key]
    if name and name in notes:
        return notes[name]
    if name:
        for k, v in notes.items():
            if k.endswith("·" + name):
                return v
    return None


def _skin_text(skin):
    """把皮肤各文本字段拼起来做关键词匹配。"""
    parts = []
    for key in ("accessWay", "szLabelTitle", "szDesc", "szTitle", "szHeroTitle"):
        val = skin.get(key)
        if val:
            parts.append(str(val))
    for key in ("classTypeName", "classType"):
        val = skin.get(key)
        if isinstance(val, list):
            parts.extend(str(x) for x in val)
        elif val:
            parts.append(str(val))
    return " ".join(parts)


def skin_key(skin):
    """生成「英雄·皮肤名」索引键。"""
    hero = str(skin.get("szHeroTitle") or "").strip()
    name = str(skin.get("szTitle") or "").strip()
    return "%s·%s" % (hero, name) if hero and name else name


def judge(skin, onsale=None):
    """判定单款皮肤,返回 {verdict, reason, rarity, price}。

    onsale: 可选的「英雄·皮肤名」集合,表示当前商城在售/正在直售返场的皮肤。
    """
    name = str(skin.get("szTitle") or "").strip()
    full_key = skin_key(skin)
    price = skin.get("iPrice") or 0
    sz_class = str(skin.get("szClass") or "")
    rarity = RARITY_MAP.get(sz_class, sz_class or "未知")

    def out(verdict, reason, rarity=rarity, price=price):
        return {"verdict": verdict, "reason": reason, "rarity": rarity, "price": price}

    # 1a. 你的人工标注(管理页面点选,优先级最高)
    mine = _lookup(user_notes(), full_key, name)
    if mine:
        return out(mine.get("gift", UNKNOWN),
                   mine.get("reason") or "你的人工标注",
                   mine.get("rarity", rarity))

    # 1b. 内置皮肤级标注
    note = _lookup(SKIN_NOTES, full_key, name)
    if note:
        return out(note.get("gift", UNKNOWN), note.get("reason", "内置标注"),
                   note.get("rarity", rarity))

    # 2. 当前在售名单(正在直售/正在直售返场)
    if onsale and (full_key in onsale or (name and name in onsale)):
        return out(GIFTABLE, "当前商城在售/正在直售返场,可直接赠送")

    text = _skin_text(skin)

    # 3. 永久不可赠送
    for kw in HARD_NO_KEYWORDS:
        if kw in text:
            return out(NOT_GIFTABLE, "命中规则[%s],绑定账号无法转移" % kw)

    # 4. 限定/限时 -> 等返场窗口
    for kw in ON_RETURN_KEYWORDS:
        if kw in text:
            return out(ON_RETURN, "命中规则[%s],限时售卖,需等直售返场窗口" % kw)

    # 5. 待确认
    for kw in UNKNOWN_KEYWORDS:
        if kw in text:
            return out(UNKNOWN, "命中规则[%s],返场形式不定" % kw)

    # 6. 有价格 -> 常驻直售
    if price and int(price) > 0:
        return out(GIFTABLE, "常驻商城直售(在售状态以游戏内为准)")
    return out(UNKNOWN, "未识别类型且无点券价格,请手动确认")
