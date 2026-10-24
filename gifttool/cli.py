"""王者送礼助手 - 命令行入口。

朋友档案:
  # 建档(每个朋友一个档案,后续所有操作按档案名引用)
  python3 -m gifttool friends add 老王 --camp-id 123456789 --role "微信区·安卓" \
      --note "开黑时说他本命公孙离"

  # 想到什么随时记,英雄会自动解析进档案
  python3 -m gifttool note 老王 "今天聊到他也想要瑶的时之祈愿"
  python3 -m gifttool watch 老王 --add-skin 公孙离·祈雪灵祝 --add-hero 貂蝉

  python3 -m gifttool friends list
  python3 -m gifttool friends show 老王

生成报告:
  python3 -m gifttool --demo                      # 示例数据跑通全流程
  python3 -m gifttool --demo --profile 老王        # 用档案的关注英雄参与筛选
  python3 -m gifttool --ck "userId&&token" --profile 老王
  python3 -m gifttool --import dumps/skin_info.json --profile 老王   # 离线数据导入

返场窗口名单(皮肤在商城返场时加进来,追踪立刻会提醒):
  python3 -m gifttool onsale add 公孙离·蜜橘之夏
  python3 -m gifttool onsale list
"""

import argparse
import json
import os
import sys

from . import camp, demo_data, herodb, pipeline, profiles, report

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMP_DIR = os.path.join(_ROOT, "dumps")
ONSALE_FILE = os.path.join(_ROOT, "data", "onsale.json")

SUBCOMMANDS = {"run", "friends", "note", "watch", "onsale", "import", "serve"}


# ---------------------------------------------------------------
# 输出
# ---------------------------------------------------------------

def _print_summary(rep):
    s = rep["summary"]
    friend = s["friend"] or {}
    hot = [a for a in (rep.get("alerts") or []) if a["level"] == "hot"]
    print("=" * 62)
    print("档案: %s  角色: %s  区服: %s"
          % (s.get("profile_name") or "-", friend.get("name", "?"), friend.get("server", "-")))
    print("他已有皮肤 %s 款" % s["owned"])
    print("本次分析英雄 %d 个(常用 ∪ 战力 ∪ 你备注/关注的) · 这些英雄里他缺 %d 款皮肤"
          % (s["hero_count"], s.get("missing_total", 0)))
    print("结论: 现在就能送 %d | 要等返场 %d | 永远不能送 %d | 待确认 %d"
          % (s["giftable_total"], s["on_return_total"],
             s["not_giftable_total"], s["unknown_total"]))
    if s.get("onsale_count"):
        print("在售名单已加载 %d 条" % s["onsale_count"])

    nxt = ((s.get("next_return") or {}).get("next"))
    if nxt:
        dl = nxt.get("days_left")
        when = ("已过 %d 天" % abs(dl)) if isinstance(dl, int) and dl < 0 else (
            ("就是今天" if dl == 0 else "还有 %d 天" % dl) if isinstance(dl, int) else "日期待确认")
        print("★ 离目标清单最近的返场: %s·%s · %s 返场(%s)%s"
              % (nxt.get("hero", ""), nxt.get("skin", ""), nxt.get("date", ""), when,
                 " · 官方已公告" if nxt.get("announced") else ""))
    else:
        print("离目标清单最近的返场: 还没登记返场日期"
              "(用 watch 档案名 --set-return 公孙离·祈雪灵祝 2026-10-20)")
    print("-" * 62)

    if rep.get("alerts"):
        print("追踪提醒:")
        for a in rep["alerts"]:
            print("  [%s] %s" % ({"hot": "可送", "warn": "注意", "info": "变化"}.get(a["level"], "-"),
                                 a["text"]))
        print("-" * 62)

    watch = rep.get("watch") or {}
    if watch.get("items"):
        print("关注皮肤:")
        for i in watch["items"]:
            print("  %-14s %-10s %s" % (i["key"], i["verdict"], i["reason"]))
        print("-" * 62)

    for h in rep["heroes"]:
        print("  %-8s [%s] 场次 %-5s 战力 %-6s 可送 %d · 待返场 %d · 不可送 %d"
              % (h["name"], h["sources"], h["games"] or "-", h["power"] or "-",
                 len(h["giftable"]), len(h["on_return"]), len(h["not_giftable"])))
        for sk in h["giftable"]:
            print("      [现在可送] %s(%s, %s点券)"
                  % (sk["szTitle"], sk["gift"]["rarity"], sk["gift"]["price"]))
        for sk in h["on_return"]:
            print("      [等返场  ] %s(%s, %s点券)"
                  % (sk["szTitle"], sk["gift"]["rarity"], sk["gift"]["price"]))
    print("=" * 62)
    if hot:
        print("!! 有 %d 条可送提醒,见上方 [可送] 行或报告页顶部" % len(hot))


def _dump(payload, name, tag):
    """把原始响应落盘,便于离线复跑与排查加密问题。"""
    path = os.path.join(DUMP_DIR, tag)
    os.makedirs(path, exist_ok=True)
    full = os.path.join(path, name)
    with open(full, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return full


# ---------------------------------------------------------------
# 数据源
# ---------------------------------------------------------------

def _pick_role(resp):
    """从 allrolelistv3 响应里挑第一个角色(防御性解析)。"""
    for d in pipeline._iter_dicts(resp):
        rid = d.get("roleId") or d.get("roleID")
        if rid:
            name = d.get("roleName") or d.get("nickName") or d.get("name") or ""
            server = d.get("serverName") or d.get("areaName") or d.get("gameAreaName") or ""
            return {"roleId": str(rid), "name": str(name), "server": str(server)}
    return {"roleId": "", "name": "", "server": ""}


def load_imported(path):
    """从本地 JSON 载入营地数据(离线/迂回路线)。

    支持三种形态:
      1. 完整导出: {"skin_info": {...}, "profile_hero": {...}, "friend": {...}}
      2. 单个接口响应原样保存: {"heroSkinConfList": ...} 或 {"data": {"heroSkinConfList": ...}}
      3. 目录: 里面放 skin_info.json / profile_hero.json
    """
    if os.path.isdir(path):
        skin_p = os.path.join(path, "skin_info.json")
        hero_p = os.path.join(path, "profile_hero.json")
        friend_p = os.path.join(path, "friend.json")
        skin = json.load(open(skin_p, encoding="utf-8")) if os.path.exists(skin_p) else {}
        hero = json.load(open(hero_p, encoding="utf-8")) if os.path.exists(hero_p) else {}
        friend = json.load(open(friend_p, encoding="utf-8")) if os.path.exists(friend_p) else {}
        return _unwrap(skin), _unwrap(hero), friend

    raw = json.load(open(path, encoding="utf-8"))
    if isinstance(raw, dict) and "skin_info" in raw:
        return (_unwrap(raw["skin_info"]), _unwrap(raw.get("profile_hero") or {}),
                raw.get("friend") or {})
    return _unwrap(raw), {}, {}


def _unwrap(data):
    """剥掉接口外层,拿到含 heroSkinConfList 的那一层。"""
    if isinstance(data, dict) and "heroSkinConfList" in data:
        return data
    for d in pipeline._iter_dicts(data):
        if "heroSkinConfList" in d:
            return d
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------
# run
# ---------------------------------------------------------------

def _resolve_target(args, store):
    """定位目标: 返回 (profile, friend_key)。friend_key 是营地ID。"""
    profile = None
    key = args.profile or (args.friend if not str(args.friend or "").isdigit() else None)
    if key:
        profile = store.resolve(key)
        if args.profile and not profile:
            print("找不到档案「%s」,可用档案:" % args.profile)
            _list_friends(store)
            raise SystemExit(2)
    friend_key = str(args.friend or "")
    if profile:
        friend_key = str(profile.get("camp_id") or friend_key)
        if not friend_key:
            raise SystemExit("档案「%s」没有填营地ID,先执行: "
                             "python3 -m gifttool friends add %s --camp-id 你的营地ID"
                             % (profile["name"], profile["name"]))
    return profile, friend_key


def _resolve_all_roles(args, store):
    """把 --all 展开成多个档案名(批量刷新用)。"""
    if not getattr(args, "all", False):
        return None
    return [f["name"] for f in store.friends]


def run_report(args, store, profile=None, friend_key=None, demo=False):
    if demo:
        rep = demo_data.demo_report(top_n=args.top, profile=profile)
        friend = dict(demo_data.DEMO_FRIEND)
        if profile:
            friend["name"] = profile.get("name", friend["name"])
            rep["summary"]["profile_name"] = profile["name"]
            rep["summary"]["profile_role"] = profile.get("role") or ""
        rep["summary"]["friend"] = friend
    elif args.import_file:
        skin_info, hero_resp, friend = load_imported(args.import_file)
        if not skin_info or "heroSkinConfList" not in skin_info:
            print("导入文件里没有 heroSkinConfList 字段,无法解析。")
            print("需要的是 h5getheroskinlist 接口的响应体(或含它的完整导出)。")
            return 1
        if not friend:
            friend = {"name": (profile or {}).get("name", "导入目标"), "roleId": "", "server": ""}
        print("已导入: %s" % os.path.abspath(args.import_file))
        rep = pipeline.build_report(friend, skin_info, hero_resp,
                                    top_n=args.top, profile=profile)
    else:
        client = camp.CampClient(ck=args.ck)

        print("[1/4] 解析角色(营地ID %s)..." % friend_key)
        roles_resp = client.resolve_roles(friend_key)
        friend = _pick_role(roles_resp)
        if not friend["roleId"]:
            print("  未能从响应中解析出角色,原始响应前 500 字符:")
            print("  " + json.dumps(roles_resp, ensure_ascii=False)[:500])
            print("  请把这段响应反馈给开发者以补充解析逻辑。")
            return 1
        print("  角色: %s  区服: %s  roleId=%s"
              % (friend["name"], friend["server"], friend["roleId"]))

        print("[2/4] 拉取皮肤目录与战力...")
        skin_raw = client.get_skin_info(friend_key)
        skin_info = _unwrap(skin_raw)
        if "heroSkinConfList" not in skin_info:
            print("  皮肤接口响应异常,前 500 字符:")
            print("  " + json.dumps(skin_raw, ensure_ascii=False)[:500])
            print("  (2026-03 后营地升级过加密,若持续失败请更新客户端版本号或换 CK)")
            return 1

        print("[3/4] 拉取常用英雄...")
        try:
            hero_resp = _unwrap(client.get_profile_hero_list(friend_key, friend["roleId"]))
        except camp.CampError as e:
            print("  常用英雄接口失败(%s),将只按战力+关注英雄筛选。" % e)
            hero_resp = {}

        print("[4/4] 判定与生成...")
        rep = pipeline.build_report(friend, skin_info, hero_resp,
                                    top_n=args.top, profile=profile)

        if args.save_dump:
            tag = (profile or {}).get("name") or friend_key
            _dump(skin_info, "skin_info.json", tag)
            _dump(hero_resp, "profile_hero.json", tag)
            _dump(friend, "friend.json", tag)
            print("  原始数据已存到 dumps/%s/ (可用 --import 离线复跑)" % tag)

    _print_summary(rep)

    if profile:
        name = profile.get("name")
        out = args.out or os.path.join(_ROOT, "output", "%s.html" % name)
    else:
        out = args.out or os.path.join(_ROOT, "output", "gift_report.html")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(report.render(rep))
    print("HTML 报告已生成: %s" % os.path.abspath(out))

    # 记录本次运行(关注皮肤快照 + 缺失清单),下次运行才能对比出变化
    if profile and not demo:
        watch = rep.get("watch") or {}
        snapshot = dict(watch.get("snapshot") or {})
        snapshot["__hero_missing__"] = watch.get("hero_missing") or {}
        store.record_run(profile, rep["summary"], snapshot)
        print("档案「%s」已更新:%d 条提醒记入追踪" % (profile["name"], len(rep.get("alerts") or [])))
    elif profile:
        print("(示例数据不写入追踪历史,避免污染对比快照)")
    return 0


# ---------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------

def _list_friends(store):
    if not store.friends:
        print("还没有档案。建一个: python3 -m gifttool friends add 老王 --camp-id 123456789")
        return
    print("%-3s %-12s %-14s %-6s %-6s %-6s %s"
          % ("#", "档案名", "营地ID", "英雄", "皮肤", "备注", "最近一次"))
    for i, f in enumerate(store.friends, 1):
        info = profiles.summarize(f)
        print("%-3d %-12s %-14s %-6d %-6d %-6d %s"
              % (i, info["name"], info["camp_id"] or "-", info["heroes"],
                 info["skins"], info["notes"], info["last_run"]))
    print("共 %d 个档案" % len(store.friends))


def cmd_friends(args, store):
    if args.action == "list":
        _list_friends(store)
        return 0

    if args.action == "add":
        name = args.name or args.target
        if not name:
            print("请给出档案名: friends add 老王 --camp-id 123456789")
            return 2
        try:
            f = store.add(name, camp_id=args.camp_id, role=args.role, note=args.note)
        except KeyError as e:
            print(e.args[0])
            return 2
        print("已建档: %s(营地ID %s)" % (f["name"], f["camp_id"] or "未填"))
        if args.note:
            _report_note(f)
        return 0

    key = args.name or args.target
    if args.action == "show":
        f = store.require(key)
        _show_friend(f)
        return 0

    if args.action in ("rm", "remove", "delete"):
        f = store.remove(key)
        print("已删除档案: %s" % f["name"])
        return 0

    print("未知操作: %s" % args.action)
    return 2


def _show_friend(f):
    print("=" * 62)
    print("档案: %s   营地ID: %s   区服: %s" % (f["name"], f.get("camp_id") or "-", f.get("role") or "-"))
    print("建立: %s   更新: %s" % (f.get("created_at", "-"), f.get("updated_at", "-")))
    print("-" * 62)
    print("关注英雄(%d):" % len(f.get("watch_heroes") or []))
    for h in (f.get("watch_heroes") or []):
        print("   %-8s (ID %s) ← %s" % (h.get("name"), h.get("heroId"), h.get("source", "")))
    print("关注皮肤(%d):" % len(f.get("watch_skins") or []))
    from . import watch as watch_mod
    for s in (f.get("watch_skins") or []):
        rd = s.get("return_date") or ""
        dl = watch_mod.days_left(rd)
        mark = ""
        if rd:
            mark = "  [返场 %s%s]" % (rd, " 还有 %d 天" % dl if isinstance(dl, int) and dl >= 0 else " 已过")
        print("   %-16s ← %s%s" % (s.get("key") or s.get("skin"), s.get("source", ""), mark))
    print("备注时间线(%d 条):" % len(f.get("notes") or []))
    for n in (f.get("notes") or []):
        tags = []
        if n.get("parsed_heroes"):
            tags.append("英雄:" + "/".join(n["parsed_heroes"]))
        if n.get("parsed_skins"):
            tags.append("皮肤:" + "/".join(n["parsed_skins"]))
        print("   [%s] %s" % (n.get("at", ""), n.get("text", "")))
        print("        解析 → %s" % ("; ".join(tags) if tags else "未识别到英雄/皮肤"))
    runs = f.get("runs") or []
    if runs:
        last = runs[-1]
        print("最近一次运行: %s (可送 %s / 待返场 %s / 不可送 %s)"
              % (last.get("at"), last.get("giftable"), last.get("on_return"), last.get("not_giftable")))
    print("=" * 62)


def _report_note(f):
    last = (f.get("notes") or [])[-1] if f.get("notes") else None
    if not last:
        return
    hs = "/".join(last.get("parsed_heroes") or []) or "无"
    ss = "/".join(last.get("parsed_skins") or []) or "无"
    print("备注已记录 · 自动解析出 英雄[%s] 皮肤[%s]" % (hs, ss))
    if last.get("parsed_heroes") or last.get("parsed_skins"):
        print("(已加入档案关注列表,下次生成报告会自动纳入筛选)")


def cmd_note(args, store):
    f = store.require(args.target)
    if not args.text:
        print("请给出备注内容: note 老王 \"他说喜欢公孙离\"")
        return 2
    store.add_note(f, args.text)
    _report_note(f)
    return 0


def cmd_watch(args, store):
    f = store.require(args.target)
    db = store.db
    changed = []

    for key in args.add_skin or []:
        hit = herodb.find_skin(key, db)
        if not hit:
            print("! 认不出这个皮肤名: %s(格式如「公孙离·祈雪灵祝」)" % key)
            continue
        hid, hero, skin = hit
        if store.add_watch_skin(f, hid, skin, source="手动添加"):
            changed.append("+皮肤 %s·%s" % (hero, skin))

    for key in args.add_hero or []:
        hit = db.by_name.get(key) or db.by_name.get(db.aliases.get(key, ""))
        if not hit:
            print("! 认不出这个英雄: %s" % key)
            continue
        if store.add_watch_hero(f, hit["id"], source="手动添加"):
            changed.append("+英雄 %s" % hit["name"])

    for key in args.rm_skin or []:
        n = store.remove_watch_skin(f, key)
        changed.append("-皮肤 %s (%d)" % (key, n))

    for key in args.rm_hero or []:
        n = store.remove_watch_hero(f, key)
        changed.append("-英雄 %s (%d)" % (key, n))

    for pair in (getattr(args, "set_return", None) or []):
        skin_key, date_str = pair[0], pair[1]
        if date_str.strip() in ("-", "none", "clear"):
            date_str = ""
        t = store.set_watch_skin_date(f, skin_key, date_str,
                                      announced=bool(getattr(args, "announced", False)))
        if t is None:
            print("! 这个皮肤不在关注列表里: %s(先用 --add-skin 加上)" % skin_key)
            continue
        changed.append("返场日期 %s → %s" % (skin_key, date_str or "已清除"))

    if not changed:
        _show_friend(f)
        return 0
    print("档案「%s」已更新:" % f["name"])
    for c in changed:
        print("   " + c)
    return 0


def cmd_onsale(args, store):
    path = ONSALE_FILE
    items = []
    if os.path.exists(path):
        try:
            items = json.load(open(path, encoding="utf-8"))
        except (ValueError, OSError):
            items = []

    if args.action == "list":
        if not items:
            print("在售/返场名单为空。皮肤在商城返场时加进来,追踪会立刻提醒可送:")
            print("  python3 -m gifttool onsale add 公孙离·蜜橘之夏")
            return 0
        for x in items:
            print("   " + str(x))
        print("共 %d 条(文件: %s)" % (len(items), path))
        return 0

    key = (args.name or "").strip()
    if not key:
        print("请给出皮肤名,如: onsale add 公孙离·蜜橘之夏")
        return 2

    if args.action == "add":
        if key in items:
            print("已在名单里: %s" % key)
            return 0
        items.append(key)
    elif args.action in ("rm", "remove"):
        items = [x for x in items if x != key]
    else:
        print("未知操作: %s" % args.action)
        return 2

    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(items, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("在售名单已更新(%d 条): %s" % (len(items), path))
    print("提示: 下次运行报告时,命中名单的皮肤会直接判为「可赠送」")
    return 0


def cmd_import(args, store):
    """离线导入营地对局数据 —— 设备抓不了包时的迂回通道。"""
    path = args.import_file
    if not path:
        print("请给出数据文件: --import dumps/老王/skin_info.json")
        return 2
    if not os.path.exists(path):
        print("文件不存在: %s" % path)
        return 2

    profile = None
    if args.profile:
        profile = store.resolve(args.profile)
        if not profile:
            print("找不到档案「%s」" % args.profile)
            _list_friends(store)
            return 2
    args.demo = False
    return run_report(args, store, profile=profile,
                      friend_key=(profile or {}).get("camp_id") if profile else None)


# ---------------------------------------------------------------
# 入口
# ---------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="gifttool",
        description="王者送礼助手: 给每个朋友建档,查他缺的、可赠送的皮肤,并追踪返场窗口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="sub")

    # run
    r = sub.add_parser("run", help="生成送礼报告(默认命令)")
    r.add_argument("--demo", action="store_true", help="使用内置示例数据跑通全流程")
    r.add_argument("--ck", help="你的营地 CK,格式 userId&&token(抓包获得,务必用小号)")
    r.add_argument("--friend", help="好友营地ID,或档案名")
    r.add_argument("--profile", help="朋友档案名(建档后所有操作都按档案走)")
    r.add_argument("--all", action="store_true", help="批量刷新所有档案(配合 --demo 可预览)")
    r.add_argument("--import", dest="import_file", help="从本地 JSON 导入营地数据(离线/迂回)")
    r.add_argument("--save-dump", action="store_true", help="把原始响应存到 dumps/ 以便离线复跑")
    r.add_argument("--top", type=int, default=10, help="常用/战力各取前 N 个英雄,默认 10")
    r.add_argument("--out", help="输出 HTML 路径")

    # friends
    f = sub.add_parser("friends", help="朋友档案管理")
    f.add_argument("action", choices=["list", "add", "show", "rm", "remove", "delete"])
    f.add_argument("name", nargs="?", help="档案名(位置参数)")
    f.add_argument("--camp-id", help="好友营地ID")
    f.add_argument("--role", help="区服备注,如「微信区·安卓」")
    f.add_argument("--note", help="建档时顺便写一条备注")

    # note
    n = sub.add_parser("note", help="给某人的档案追加一条备注(自动解析英雄/皮肤)")
    n.add_argument("target", help="档案名")
    n.add_argument("text", nargs="?", help="备注内容")

    # watch
    w = sub.add_parser("watch", help="调整某个档案的关注英雄/皮肤")
    w.add_argument("target", help="档案名")
    w.add_argument("--add-skin", action="append", help="添加关注皮肤,如 公孙离·祈雪灵祝")
    w.add_argument("--add-hero", action="append", help="添加关注英雄,如 公孙离")
    w.add_argument("--rm-skin", action="append", help="移除关注皮肤")
    w.add_argument("--rm-hero", action="append", help="移除关注英雄")
    w.add_argument("--set-return", nargs=2, action="append", metavar=("皮肤", "日期"),
                   help="登记返场日期(倒计时卡片用它),如 --set-return 公孙离·祈雪灵祝 2026-10-20;"
                        "日期填 - 表示清除")
    w.add_argument("--announced", action="store_true",
                   help="配合 --set-return,表示这是官方公告的确定日期")

    # onsale
    o = sub.add_parser("onsale", help="维护「当前商城在售/正在返场」名单")
    o.add_argument("action", choices=["list", "add", "rm", "remove"])
    o.add_argument("name", nargs="?", help="皮肤名,如 公孙离·蜜橘之夏")

    # import
    i = sub.add_parser("import", help="离线导入营地数据并生成报告")
    i.add_argument("--import", dest="import_file", help="数据文件或目录")
    i.add_argument("--profile", help="档案名")
    i.add_argument("--top", type=int, default=10)
    i.add_argument("--out")

    # serve
    s = sub.add_parser("serve", help="启动本地档案管理页面(浏览器里建档/写备注/标注皮肤)")
    s.add_argument("--port", type=int, default=8765, help="端口,默认 8765")
    s.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # 兼容旧用法: 不带子命令时默认走 run
    if not argv or argv[0] not in SUBCOMMANDS:
        argv = ["run"] + argv

    parser = build_parser()
    args = parser.parse_args(argv)
    store = profiles.Store()

    if args.sub == "friends":
        return cmd_friends(args, store)
    if args.sub == "note":
        return cmd_note(args, store)
    if args.sub == "watch":
        return cmd_watch(args, store)
    if args.sub == "onsale":
        return cmd_onsale(args, store)
    if args.sub == "import":
        return cmd_import(args, store)
    if args.sub == "serve":
        from . import server
        server.serve(port=args.port, open_browser=not args.no_open)
        return 0

    # run
    if args.all:
        names = _resolve_all_roles(args, store) or []
        if not names:
            print("没有档案可刷新,先建档: python3 -m gifttool friends add 老王 --camp-id 123")
            return 0
        rc = 0
        for nm in names:
            prof = store.resolve(nm)
            print("\n### 刷新档案: %s" % nm)
            rc |= run_report(args, store, profile=prof,
                             friend_key=prof.get("camp_id"), demo=profile_demo(args))
        return rc

    profile, friend_key = _resolve_target(args, store)
    demo = profile_demo(args)
    if not demo and not args.import_file and not (args.ck and friend_key):
        parser.error("需要 --ck 和 --friend(或 --profile / --import / --demo)")
    try:
        rc = run_report(args, store, profile=profile, friend_key=friend_key, demo=demo)
    except camp.CampError as e:
        print("营地接口错误: %s" % e)
        return 1
    return rc


def profile_demo(args):
    """--demo 时若指定了真实档案,用档案数据但换成示例营地数据。"""
    return bool(getattr(args, "demo", False))


if __name__ == "__main__":
    sys.exit(main())
