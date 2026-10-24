"""多朋友档案系统。

每个朋友 = 一个独立档案 = 一个独立送礼目标。档案内容:

  name          备注名(你认得就行,如"老王""大学室友")
  camp_id       营地ID(王者营地 App 里复制)
  role          区服备注(如"微信区·安卓"),用于提醒同大区同系统才能送
  notes         备注时间线 —— 想到什么写什么,支持自然语言
  watch_heroes  关注英雄(来自备注自动解析,或手动加)
  watch_skins   关注皮肤(来自备注自动解析,或手动加)——追踪返场用
  runs          历史运行记录,用于对比出"新增缺失/新上架"

存储:data/friends.json(纯文本,可以直接手改)
"""

import datetime
import json
import os
import re

from . import herodb

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRIENDS_FILE = os.path.join(_ROOT, "data", "friends.json")
SCHEMA_VERSION = 2


def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _slug(name):
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", (name or "").strip()).strip("-")
    return s or "friend"


class Store:
    def __init__(self, path=None, db=None):
        self.path = path or FRIENDS_FILE
        self.db = db or herodb.load()
        self.data = self._load()

    # ---------- 读写 ----------

    def _load(self):
        if not os.path.exists(self.path):
            return {"version": SCHEMA_VERSION, "friends": []}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (ValueError, OSError):
            return {"version": SCHEMA_VERSION, "friends": []}
        if isinstance(data, list):  # 兼容早期纯数组格式
            data = {"version": SCHEMA_VERSION, "friends": data}
        data.setdefault("friends", [])
        return data

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)

    # ---------- 查询 ----------

    @property
    def friends(self):
        return self.data["friends"]

    def resolve(self, key):
        """按档案名/营地ID/序号定位档案。支持子串模糊匹配。"""
        key = str(key or "").strip()
        if not key:
            return None
        for f in self.friends:
            if f.get("name") == key or str(f.get("camp_id") or "") == key:
                return f
        if key.isdigit():
            idx = int(key) - 1
            if 0 <= idx < len(self.friends):
                return self.friends[idx]
        for f in self.friends:
            if key and key in (f.get("name") or ""):
                return f
        return None

    def require(self, key):
        f = self.resolve(key)
        if not f:
            raise KeyError("档案不存在: %s (先用 friends add 建档)" % key)
        return f

    # ---------- 增删改 ----------

    def add(self, name, camp_id="", role="", note=None):
        existing = self.resolve(name)
        if existing:
            raise KeyError("档案已存在: %s" % existing.get("name"))
        f = {
            "name": name,
            "camp_id": str(camp_id or ""),
            "role": role or "",
            "created_at": now_str(),
            "updated_at": now_str(),
            "notes": [],
            "watch_heroes": [],
            "watch_skins": [],
            "runs": [],
        }
        self.friends.append(f)
        if note:
            self.add_note(f, note)
        self.save()
        return f

    def remove(self, key):
        f = self.require(key)
        self.friends.remove(f)
        self.save()
        return f

    def touch(self, f):
        f["updated_at"] = now_str()

    # ---------- 备注与解析 ----------

    def add_note(self, f, text):
        """写入一条备注,并自动解析出英雄/皮肤,合并进关注列表。"""
        text = (text or "").strip()
        if not text:
            return {"heroes": [], "skins": []}
        parsed = herodb.scan(text, self.db)
        entry = {
            "at": now_str(), "text": text,
            "parsed_heroes": [h["name"] for h in parsed["heroes"]],
            "parsed_skins": ["%s·%s" % (s["hero"], s["skin"]) for s in parsed["skins"]],
        }
        f.setdefault("notes", []).append(entry)

        added_h, added_s = [], []
        for h in parsed["heroes"]:
            if self.add_watch_hero(f, h["heroId"], source="备注: %s" % h["reason"], quiet=True):
                added_h.append(h["name"])
        for s in parsed["skins"]:
            if self.add_watch_skin(f, s["heroId"], s["skin"],
                                   source="备注: %s" % s["reason"], quiet=True):
                added_s.append("%s·%s" % (s["hero"], s["skin"]))
        self.touch(f)
        self.save()
        return {"heroes": added_h, "skins": added_s, "parsed": parsed, "entry": entry}

    def add_watch_hero(self, f, hero_id, source="手动添加", quiet=False):
        hero_id = int(hero_id)
        lst = f.setdefault("watch_heroes", [])
        if any(int(x.get("heroId", -1)) == hero_id for x in lst):
            return False
        name = self.db.hero_name(hero_id) or str(hero_id)
        lst.append({"heroId": hero_id, "name": name, "source": source, "added_at": now_str()})
        if not quiet:
            self.touch(f)
            self.save()
        return True

    def add_watch_skin(self, f, hero_id, skin, source="手动添加", quiet=False,
                       return_date=None, announced=False):
        lst = f.setdefault("watch_skins", [])
        key = "%s·%s" % (self.db.hero_name(hero_id), skin) if hero_id else skin
        exists = None
        for x in lst:
            if (x.get("key") or "%s·%s" % (x.get("hero"), x.get("skin"))) == key:
                exists = x
                break
        if exists is not None:
            # 已存在时不重复加,但如果这次带了新日期/公告信息就补上
            if return_date and not exists.get("return_date"):
                exists["return_date"] = str(return_date)[:10]
                exists["announced"] = bool(announced)
                if not quiet:
                    self.touch(f)
                    self.save()
            return False
        lst.append({
            "key": key, "heroId": int(hero_id) if hero_id else None,
            "hero": self.db.hero_name(hero_id) if hero_id else "",
            "skin": skin, "source": source, "added_at": now_str(),
            "return_date": str(return_date)[:10] if return_date else "",
            "announced": bool(announced),
        })
        if not quiet:
            self.touch(f)
            self.save()
        return True

    def set_watch_skin_date(self, f, key, date_str, announced=False):
        """给某款关注皮肤写/清掉返场日期(倒计时卡片就靠它)。"""
        key = (key or "").strip()
        target = None
        for x in (f.get("watch_skins") or []):
            if key in ((x.get("key") or ""), x.get("skin") or "",
                       "%s·%s" % (x.get("hero"), x.get("skin"))):
                target = x
                break
        if target is None:
            return None
        date_str = (date_str or "").strip()[:10]
        if date_str:
            target["return_date"] = date_str
            target["announced"] = bool(announced)
        else:
            target.pop("return_date", None)
            target.pop("announced", None)
        self.touch(f)
        self.save()
        return target

    def remove_watch_skin(self, f, key):
        key = (key or "").strip()
        lst = f.setdefault("watch_skins", [])
        before = len(lst)
        f["watch_skins"] = [
            x for x in lst
            if key not in ((x.get("key") or ""), x.get("skin") or "", x.get("hero") or "")
        ]
        self.touch(f)
        self.save()
        return before - len(f["watch_skins"])

    def remove_watch_hero(self, f, key):
        key = (key or "").strip()
        lst = f.setdefault("watch_heroes", [])
        before = len(lst)
        f["watch_heroes"] = [
            x for x in lst
            if key not in ((x.get("name") or ""), str(x.get("heroId") or ""))
        ]
        self.touch(f)
        self.save()
        return before - len(f["watch_heroes"])

    # ---------- 运行记录 ----------

    def record_run(self, f, summary, snapshot):
        f.setdefault("runs", []).append({
            "at": now_str(),
            "giftable": summary.get("giftable_total", 0),
            "on_return": summary.get("on_return_total", 0),
            "not_giftable": summary.get("not_giftable_total", 0),
            "snapshot": snapshot,
        })
        # 只保留最近 30 次,防止文件无限膨胀
        if len(f["runs"]) > 30:
            f["runs"] = f["runs"][-30:]
        self.touch(f)
        self.save()

    def last_run(self, f):
        runs = f.get("runs") or []
        return runs[-1] if runs else None


# ---------------------------------------------------------------
# 档案展示辅助
# ---------------------------------------------------------------

def hero_set(f):
    """档案里的关注英雄 ID 集合。"""
    return {int(x["heroId"]) for x in (f.get("watch_heroes") or []) if x.get("heroId")}


def watch_skin_map(f):
    """关注皮肤 -> {key: 记录}。"""
    out = {}
    for x in (f.get("watch_skins") or []):
        key = x.get("key") or "%s·%s" % (x.get("hero"), x.get("skin"))
        out[key] = x
    return out


def summarize(f):
    """档案一句话概览,用于 CLI 列表。"""
    return {
        "name": f.get("name", ""),
        "camp_id": f.get("camp_id", ""),
        "role": f.get("role", ""),
        "notes": len(f.get("notes") or []),
        "heroes": len(f.get("watch_heroes") or []),
        "skins": len(f.get("watch_skins") or []),
        "last_run": (self_run_at(f) or "-"),
        "updated_at": f.get("updated_at", ""),
    }


def self_run_at(f):
    runs = f.get("runs") or []
    return runs[-1]["at"] if runs else ""
