"""核心流水线: 合并英雄集合 -> 计算缺失皮肤 -> 赠送判定 -> 汇总输出。"""

import datetime
import json
import os

from . import herodb, profiles as profiles_mod, rules
from . import watch as watch_mod

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ONSALE_FILE = os.path.join(_ROOT, "data", "onsale.json")


def load_onsale(path=None):
    """读取「当前在售/正在直售返场」名单(JSON 字符串数组,元素为「英雄·皮肤名」)。

    文件不存在时返回空集合。命中名单的皮肤直接判为可赠送。
    """
    path = path or ONSALE_FILE
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (ValueError, OSError):
        return set()

# 常用英雄场次/战力字段的候选键名(接口字段名随版本变化,逐个尝试)
GAME_COUNT_KEYS = ["battleCount", "useCount", "gameCount", "count", "games", "totalCount", "playCount"]
WIN_RATE_KEYS = ["winRate", "winrate", "win"]
HERO_ID_KEYS = ["heroId", "heroid", "iHeroId"]
HERO_NAME_KEYS = ["heroName", "name", "cname", "szHeroTitle"]


def _pick(d, keys, default=None):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _iter_dicts(obj):
    """深度优先遍历嵌套结构里的所有 dict,用于防御性解析未知结构的响应。"""
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            yield cur
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)


def extract_owned_skin_ids(skin_info):
    """从 h5getheroskinlist 响应中提取已拥有皮肤 ID 集合。

    heroSkinList 为已拥有皮肤列表(开源项目用法); 若结构变化导致为空,
    退化为统计 skinCountInfo.owned 的数量并在日志中提示。
    """
    owned = set()
    for skin in skin_info.get("heroSkinList") or []:
        sid = skin.get("skinId")
        if sid:
            owned.add(str(sid))
    return owned


def extract_hero_fight_power(skin_info):
    """提取各英雄战力: {heroId: power}。来源 skin_info['heroList']。"""
    result = {}
    for k, v in (skin_info.get("heroList") or {}).items():
        if isinstance(v, dict):
            power = v.get("heroFightPower") or 0
            try:
                result[int(v.get("heroId", k))] = int(power)
            except (TypeError, ValueError):
                continue
    return result


def extract_used_heroes(profile_hero_resp):
    """从 profile/herolist 响应中提取常用英雄: [{heroId, name, games}]。

    该接口响应结构未完全公开,这里用「找带 heroId 且带场次字段的 dict」的
    策略兜底; 解析不到时返回空列表,由调用方决定是否只用战力维度。
    """
    heroes = []
    seen = set()
    for d in _iter_dicts(profile_hero_resp):
        hid = _pick(d, HERO_ID_KEYS)
        if hid is None:
            continue
        try:
            hid = int(hid)
        except (TypeError, ValueError):
            continue
        games = _pick(d, GAME_COUNT_KEYS)
        if games is None:
            continue
        try:
            games = int(games)
        except (TypeError, ValueError):
            continue
        if hid in seen:
            continue
        seen.add(hid)
        heroes.append({
            "heroId": hid,
            "name": _pick(d, HERO_NAME_KEYS, ""),
            "games": games,
        })
    heroes.sort(key=lambda h: h["games"], reverse=True)
    return heroes


def merge_heroes(used_heroes, hero_power, top_n, watch_heroes=None):
    """合并英雄集合: 常用 Top N ∪ 战力 Top N ∪ 档案关注英雄,标注来源。

    watch_heroes: {heroId: name},来自朋友档案(备注解析或手动添加)。
    关注英雄不受 Top N 限制,因为它是你从聊天里确认过的信号,优先级更高。
    """
    merged = {}
    for h in used_heroes[:top_n]:
        merged[h["heroId"]] = {
            "heroId": h["heroId"], "name": h["name"],
            "games": h["games"], "power": 0, "sources": ["常用"],
        }
    power_rank = sorted(
        [(hid, p) for hid, p in hero_power.items() if p and p > 0],
        key=lambda x: x[1], reverse=True,
    )[:top_n]
    for hid, power in power_rank:
        if hid in merged:
            merged[hid]["power"] = power
            merged[hid]["sources"].append("战力")
        else:
            merged[hid] = {"heroId": hid, "name": "", "games": 0,
                           "power": power, "sources": ["战力"]}

    for hid, name in (watch_heroes or {}).items():
        hid = int(hid)
        if hid in merged:
            if "关注" not in merged[hid]["sources"]:
                merged[hid]["sources"].append("关注")
            if not merged[hid]["name"] and name:
                merged[hid]["name"] = name
        else:
            merged[hid] = {"heroId": hid, "name": name or "", "games": 0,
                           "power": hero_power.get(hid, 0), "sources": ["关注"]}
    return merged


def build_gift_rows(skin_info, hero_ids, onsale=None):
    """对给定英雄集合,计算缺失皮肤并做赠送判定。

    返回 {heroId: {"conf": heroInfo, "missing": [skinDict...]}}
    """
    conf_all = skin_info.get("heroSkinConfList") or {}
    hero_conf = skin_info.get("heroConfList") or {}
    owned = extract_owned_skin_ids(skin_info)

    # 按英雄归组全量皮肤目录
    by_hero = {}
    for sid, detail in conf_all.items():
        hid = detail.get("iHeroId")
        if hid is None:
            continue
        by_hero.setdefault(int(hid), []).append((str(sid), detail))

    result = {}
    for hid in hero_ids:
        hero_meta = hero_conf.get(str(hid), {})
        missing = []
        for sid, detail in by_hero.get(hid, []):
            if sid in owned:
                continue
            if detail.get("isHidden"):
                continue
            skin = dict(detail)
            skin["skinId"] = sid
            skin["gift"] = rules.judge(skin, onsale=onsale)
            missing.append(skin)
        missing.sort(key=lambda s: (
            rules.VERDICT_ORDER.get(s["gift"]["verdict"], 4),
            rules.RARITY_ORDER.get(s["gift"]["rarity"], 5),
            -(s["gift"]["price"] or 0),
        ))
        result[hid] = {
            "conf": {"name": hero_meta.get("name", "")},
            "missing": missing,
        }
    return result


def compute_next_return(profile, today=None):
    """在目标清单(关注皮肤)里找「已登记返场日期」中最近的一款。

    返回 {"items": [...按日期升序...], "next": 最近的一款或 None, "today": "..."}。
    已过期的日期保留在 items 里但不会被选为 next。
    """
    items = []
    for x in (profile or {}).get("watch_skins") or []:
        rd = (x.get("return_date") or "").strip()[:10]
        d = watch_mod.parse_date(rd)
        if not d:
            continue
        key = x.get("key") or "%s·%s" % (x.get("hero"), x.get("skin"))
        items.append({
            "key": key, "hero": x.get("hero") or "", "skin": x.get("skin") or "",
            "date": d.isoformat(),
            "days_left": watch_mod.days_left(rd, today),
            "announced": bool(x.get("announced")),
        })
    items.sort(key=lambda p: p["date"])
    upcoming = [p for p in items if (p["days_left"] is None or p["days_left"] >= 0)]
    return {
        "items": items,
        "next": (upcoming or items or [None])[0],
        "today": (today or datetime.date.today()).isoformat(),
    }


def build_report(friend_info, skin_info, profile_hero_resp, top_n=10, onsale=None,
                 profile=None, db=None):
    """汇总所有数据,产出报告用的纯数据结构。

    profile: 朋友档案(dict)。给了就会把关注英雄并入筛选集、额外评估关注皮肤,
             并与上次运行对比产出提醒。
    """
    if onsale is None:
        onsale = load_onsale()
    db = db or herodb.load()

    hero_power = extract_hero_fight_power(skin_info)
    used_heroes = extract_used_heroes(profile_hero_resp)

    watch_heroes = {}
    if profile:
        for x in (profile.get("watch_heroes") or []):
            if x.get("heroId") is not None:
                watch_heroes[int(x["heroId"])] = x.get("name") or db.hero_name(x["heroId"])

    merged = merge_heroes(used_heroes, hero_power, top_n, watch_heroes=watch_heroes)
    rows = build_gift_rows(skin_info, merged.keys(), onsale=onsale)

    hero_rows = []
    for hid, info in merged.items():
        missing = rows.get(hid, {}).get("missing", [])
        hero_rows.append({
            "heroId": hid,
            "name": info["name"] or rows.get(hid, {}).get("conf", {}).get("name", "")
                    or db.hero_name(hid),
            "games": info["games"],
            "power": info["power"],
            "sources": "+".join(info["sources"]),
            "watched": "关注" in info["sources"],
            "missing": missing,
            "giftable": [s for s in missing if s["gift"]["verdict"] == rules.GIFTABLE],
            "on_return": [s for s in missing if s["gift"]["verdict"] == rules.ON_RETURN],
            "unknown": [s for s in missing if s["gift"]["verdict"] == rules.UNKNOWN],
            "not_giftable": [s for s in missing if s["gift"]["verdict"] == rules.NOT_GIFTABLE],
            "missing_total": len(missing),
        })
    # 关注英雄置顶(聊天里确认过的信号最强),其余按场次、战力排
    hero_rows.sort(key=lambda h: (h["watched"], h["games"], h["power"]), reverse=True)

    # 跨英雄汇总: 现在就能送的清单(按品质、价格排序)
    wishlist = []
    for h in hero_rows:
        for s in h["giftable"]:
            wishlist.append({
                "hero": h["name"], "skin": s.get("szTitle", ""),
                "rarity": s["gift"]["rarity"], "price": s["gift"]["price"],
                "from_watch": h["watched"],
            })
    wishlist.sort(key=lambda x: (not x["from_watch"],
                                 rules.RARITY_ORDER.get(x["rarity"], 5),
                                 -(x["price"] or 0)))

    # 档案: 关注皮肤评估 + 与上次运行对比的提醒
    watch_result = None
    alerts = []
    if profile:
        watch_result = watch_mod.evaluate(profile, skin_info, onsale=onsale, db=db)
        runs = profile.get("runs") or []
        alerts = watch_mod.diff_against(runs[-1] if runs else None, watch_result)

    skin_count = skin_info.get("skinCountInfo") or {}
    next_return = compute_next_return(profile)
    summary = {
        "friend": friend_info,
        "profile_name": (profile or {}).get("name", ""),
        "profile_role": (profile or {}).get("role", ""),
        "notes": list((profile or {}).get("notes") or []),
        "owned": skin_count.get("owned", ""),
        "total": skin_count.get("totalSkinNum", ""),
        "total_value": skin_count.get("totalValue", ""),
        "hero_count": len(hero_rows),
        "missing_total": sum(h["missing_total"] for h in hero_rows),
        "giftable_total": sum(len(h["giftable"]) for h in hero_rows),
        "on_return_total": sum(len(h["on_return"]) for h in hero_rows),
        "unknown_total": sum(len(h["unknown"]) for h in hero_rows),
        "not_giftable_total": sum(len(h["not_giftable"]) for h in hero_rows),
        "onsale_count": len(onsale),
        "top_n": top_n,
        "hot_alerts": len([a for a in alerts if a["level"] == "hot"]),
        "next_return": next_return,
    }
    return {
        "summary": summary,
        "heroes": hero_rows,
        "wishlist": wishlist,
        "watch": watch_result,
        "alerts": alerts,
    }
