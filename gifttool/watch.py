"""关注皮肤追踪与返场提醒。

追踪对象是档案里的 watch_skins(可能来自备注自动解析,也可能手动加)。
每次运行都会对每款关注皮肤做三件事:

  1. 在对方皮肤目录里定位它 -> 拿到 skinId 与获取方式文本;
  2. 判断对方是否已拥有(已有就提醒"别送了");
  3. 用 rules.judge 定态,并与上次运行的快照对比,产出提醒。

关注皮肤还可以带一个 return_date(返场日期,来自官方公告或你手动填),
流水线会用它在报告顶部算「离目标清单最近的返场还有几天」。

提醒分四级:
  hot   窗口打开(变成可赠送) -> 现在就能送
  warn  确认永久不可送 / 皮肤名识别不到
  info  窗口关闭、新增缺失皮肤
"""

import datetime

from . import rules


def _norm(s):
    return (s or "").strip().replace(" ", "").replace(" ", "")


def parse_date(s):
    """把 '2026-10-20' / '2026/10/20' / '2026-10-20 10:00' 解析成 date,失败返回 None。"""
    s = (s or "").strip().replace("/", "-").replace(".", "-")
    if not s:
        return None
    s = s[:10]
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def days_left(date_str, today=None):
    """距返场还有几天(负数表示已过)。解析不了返回 None。"""
    d = parse_date(date_str)
    if not d:
        return None
    today = today or datetime.date.today()
    return (d - today).days


def _find_in_catalog(skin_info, hero_name, skin_name):
    """在对方皮肤目录里定位一款皮肤,返回 (skinId, detail) 或 (None, None)。

    先用「英雄+皮肤名」精确匹配,退化为皮肤名全局匹配。
    """
    conf = skin_info.get("heroSkinConfList") or {}
    hero_name, skin_name = _norm(hero_name), _norm(skin_name)
    loose = None
    for sid, detail in conf.items():
        if _norm(detail.get("szTitle")) != skin_name:
            continue
        if hero_name and _norm(detail.get("szHeroTitle")) == hero_name:
            return str(sid), detail
        if loose is None:
            loose = (str(sid), detail)
    return loose or (None, None)


def evaluate(profile, skin_info, onsale=None, db=None, today=None):
    """评估档案里所有关注皮肤。

    返回 {"items": [...], "snapshot": {key: {...}}, "hero_missing": {...}}
    items 每项带 return_date / days_left(没填日期则为空/None)。
    """
    from . import pipeline  # 延迟导入避免循环依赖

    today = today or datetime.date.today()
    owned = pipeline.extract_owned_skin_ids(skin_info)
    hero_conf = skin_info.get("heroConfList") or {}
    items = []
    snapshot = {}

    for raw in (profile.get("watch_skins") or []):
        key = raw.get("key") or "%s·%s" % (raw.get("hero"), raw.get("skin"))
        hero_name = raw.get("hero") or ""
        skin_name = raw.get("skin") or ""
        if not hero_name and db:
            hero_name = db.hero_name(raw.get("heroId"))

        sid, detail = _find_in_catalog(skin_info, hero_name, skin_name)
        item = {
            "key": key, "hero": hero_name, "skin": skin_name,
            "source": raw.get("source", ""), "found": bool(sid),
            "owned": False, "verdict": rules.UNKNOWN, "reason": "", "rarity": "", "price": 0,
            "return_date": (raw.get("return_date") or "")[:10],
            "announced": bool(raw.get("announced")),
            "days_left": days_left(raw.get("return_date"), today),
        }
        if sid:
            item["owned"] = sid in owned
            if not hero_name:
                item["hero"] = detail.get("szHeroTitle") or ""
            if item["owned"]:
                item["verdict"] = "已拥有"
                item["reason"] = "对方已拥有这款皮肤,不用送了"
                item["rarity"] = rules.RARITY_MAP.get(str(detail.get("szClass") or ""), "")
                item["price"] = detail.get("iPrice") or 0
            else:
                g = rules.judge(detail, onsale=onsale)
                item.update({"verdict": g["verdict"], "reason": g["reason"],
                             "rarity": g["rarity"], "price": g["price"]})
        else:
            item["verdict"] = "待确认"
            item["reason"] = "对方皮肤目录里没找到这款(可能名字记错,或该皮肤已下架隐藏)"
        items.append(item)
        snapshot[key] = {
            "verdict": item["verdict"], "owned": item["owned"],
            "found": item["found"], "hero": item["hero"],
            "price": item["price"], "return_date": item["return_date"],
        }

    # 关注英雄全体:新增缺失皮肤(曾经的"已集齐"变成有缺口)
    hero_missing = {}
    for raw in (profile.get("watch_heroes") or []):
        hid = raw.get("heroId")
        if hid is None:
            continue
        hero_missing[str(hid)] = _missing_keys_of(skin_info, owned, int(hid))

    return {"items": items, "snapshot": snapshot, "hero_missing": hero_missing}


def _missing_keys_of(skin_info, owned, hero_id):
    """某个英雄当前缺失的皮肤「英雄·皮肤名」清单。"""
    conf = skin_info.get("heroSkinConfList") or {}
    out = []
    for sid, detail in conf.items():
        if detail.get("iHeroId") is None:
            continue
        try:
            if int(detail.get("iHeroId")) != int(hero_id):
                continue
        except (TypeError, ValueError):
            continue
        if str(sid) in owned or detail.get("isHidden"):
            continue
        out.append("%s·%s" % (detail.get("szHeroTitle") or "", detail.get("szTitle") or ""))
    return sorted(out)


def diff_against(prev_run, current):
    """把本次评估结果与上次运行快照对比,产出提醒列表。"""
    alerts = []
    prev_snap = (prev_run or {}).get("snapshot") or {}
    prev_missing = ((prev_run or {}).get("hero_missing")
                    or prev_snap.get("__hero_missing__") or {})

    for item in current.get("items") or []:
        key = item["key"]
        prev = prev_snap.get(key)
        if not item["found"]:
            alerts.append({
                "level": "warn", "key": key, "title": item["skin"],
                "text": "关注列表里的「%s」在对方皮肤目录中没找到,请核对皮肤名" % key,
            })
            continue
        if item["owned"]:
            if prev is None or not prev.get("owned"):
                alerts.append({
                    "level": "info", "key": key, "title": item["skin"],
                    "text": "「%s」对方已经拥有了,从送礼清单里划掉" % key,
                })
            continue
        cur_v = item["verdict"]
        prev_v = (prev or {}).get("verdict")

        # 返场日期出现/变化时单独提醒一次(这是用户最关心的那条)
        rd = item.get("return_date") or ""
        if rd and rd != ((prev or {}).get("return_date") or ""):
            dl = item.get("days_left")
            when = "，还有 %d 天" % dl if isinstance(dl, int) and dl >= 0 else ""
            alerts.append({
                "level": "hot" if (isinstance(dl, int) and 0 <= dl <= 7) else "info",
                "key": key, "title": item["skin"],
                "text": "「%s」已登记返场日期 %s%s" % (key, rd, when),
            })

        if prev is None:
            alerts.append({
                "level": "info", "key": key, "title": item["skin"],
                "text": "新加入追踪:「%s」当前状态 %s" % (key, cur_v),
            })
        elif prev_v != cur_v:
            if cur_v == rules.GIFTABLE:
                alerts.append({
                    "level": "hot", "key": key, "title": item["skin"],
                    "text": "🎉 窗口打开了:「%s」现在可赠送(%s)"
                            % (key, item["reason"] or "商城在售"),
                })
            elif prev_v == rules.GIFTABLE:
                alerts.append({
                    "level": "info", "key": key, "title": item["skin"],
                    "text": "窗口关闭:「%s」已不在售,状态变为 %s" % (key, cur_v),
                })
            elif cur_v == rules.NOT_GIFTABLE and prev_v in (rules.ON_RETURN, rules.UNKNOWN):
                alerts.append({
                    "level": "warn", "key": key, "title": item["skin"],
                    "text": "「%s」确认为永久不可赠送(%s)" % (key, item["reason"]),
                })
            else:
                alerts.append({
                    "level": "info", "key": key, "title": item["skin"],
                    "text": "「%s」状态由 %s 变为 %s" % (key, prev_v, cur_v),
                })

    # 关注英雄的缺失清单变化
    cur_missing = current.get("hero_missing") or {}
    for hid, keys in cur_missing.items():
        old = set(prev_missing.get(hid) or [])
        if not old:
            continue  # 首次记录,不报
        new = [k for k in keys if k not in old]
        if new:
            alerts.append({
                "level": "hot", "key": "hero:%s" % hid, "title": "关注英雄新增缺失",
                "text": "你关注的英雄新增 %d 款缺失皮肤: %s" % (len(new), "、".join(new[:5])),
            })

    order = {"hot": 0, "warn": 1, "info": 2}
    alerts.sort(key=lambda a: order.get(a["level"], 3))
    return alerts


LEVEL_LABEL = {"hot": "可送提醒", "warn": "需注意", "info": "变化"}
