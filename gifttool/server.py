"""本地档案管理页面(浏览器里建档、写备注、标注皮肤)。

为什么需要它: HTML 报告是"只读"的,没法写文件。要能在页面上建档/编辑,就需要一个本地服务。
只在你自己电脑上跑(127.0.0.1),不对外、不备案。数据全部落在本机 data/ 目录里,不上传任何地方。

启动:
  python3 -m gifttool serve
然后浏览器打开 http://127.0.0.1:8765
"""

import datetime
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import cli, demo_data, herodb, pipeline, profiles, report, rules

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(_ROOT, "output")
DUMPS_DIR = os.path.join(_ROOT, "dumps")
VERDICTS = [rules.GIFTABLE, rules.ON_RETURN, rules.NOT_GIFTABLE, rules.UNKNOWN]


# ---------------------------------------------------------------
# 业务操作
# ---------------------------------------------------------------

def _state():
    store = profiles.Store()
    db = store.db
    heroes = [{"id": h["id"], "name": h["name"],
               "skins": ["%s·%s" % (h["name"], s) for s in h["skins"]]}
              for h in db.heroes]
    dumps = []
    if os.path.isdir(DUMPS_DIR):
        dumps = [d for d in os.listdir(DUMPS_DIR)
                 if os.path.isdir(os.path.join(DUMPS_DIR, d))]
    friends = []
    for f in store.friends:
        item = dict(f)
        item["has_dump"] = os.path.isdir(os.path.join(DUMPS_DIR, f["name"]))
        friends.append(item)
    return {
        "friends": friends,
        "onsale": sorted(pipeline.load_onsale()),
        "skin_notes": rules.user_notes(),
        "heroes": heroes,
        "verdicts": VERDICTS,
        "dumps": dumps,
        "today": datetime.date.today().isoformat(),
        "roots": {"output": OUTPUT_DIR, "data": os.path.join(_ROOT, "data")},
    }


def _friend_save(payload):
    store = profiles.Store()
    orig = (payload.get("orig_name") or "").strip()
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("档案名不能为空")
    if orig:
        f = store.require(orig)
        f["name"] = name
        f["camp_id"] = str(payload.get("camp_id") or "").strip()
        f["role"] = (payload.get("role") or "").strip()
        store.touch(f)
        store.save()
    else:
        f = store.add(name, camp_id=payload.get("camp_id"), role=payload.get("role"),
                      note=(payload.get("note") or "").strip() or None)
    return {"ok": True, "name": f["name"]}


def _friend_delete(payload):
    store = profiles.Store()
    f = store.remove(payload.get("key"))
    return {"ok": True, "name": f["name"]}


def _friend_note(payload):
    store = profiles.Store()
    f = store.require(payload.get("key"))
    text = (payload.get("text") or "").strip()
    if not text:
        raise ValueError("备注内容为空")
    res = store.add_note(f, text)
    return {"ok": True, "heroes": res["heroes"], "skins": res["skins"],
            "text": text, "at": res["entry"]["at"]}


def _friend_note_remove(payload):
    store = profiles.Store()
    f = store.require(payload.get("key"))
    idx = payload.get("index")
    notes = f.get("notes") or []
    if isinstance(idx, int) and 0 <= idx < len(notes):
        notes.pop(idx)
        store.touch(f)
        store.save()
    return {"ok": True}


def _friend_watch(payload):
    store = profiles.Store()
    db = store.db
    f = store.require(payload.get("key"))
    added, removed, problems = [], [], []
    for name in payload.get("add_heroes") or []:
        h = db.by_name.get(name) or db.by_name.get(db.aliases.get(name, ""))
        if not h:
            problems.append("认不出英雄: %s" % name)
            continue
        if store.add_watch_hero(f, h["id"], source="手动添加"):
            added.append(h["name"])
    for skin_key in payload.get("add_skins") or []:
        hit = herodb.find_skin(skin_key, db)
        if not hit:
            problems.append("认不出皮肤: %s" % skin_key)
            continue
        hid, hero, skin = hit
        if store.add_watch_skin(f, hid, skin, source="手动添加"):
            added.append("%s·%s" % (hero, skin))
    for name in payload.get("rm_heroes") or []:
        store.remove_watch_hero(f, name)
        removed.append(name)
    for skin_key in payload.get("rm_skins") or []:
        store.remove_watch_skin(f, skin_key)
        removed.append(skin_key)
    store.save()
    return {"ok": True, "added": added, "removed": removed, "problems": problems}


def _onsale(payload):
    path = pipeline.ONSALE_FILE
    items = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                items = json.load(fh)
        except (ValueError, OSError):
            items = []
    key = (payload.get("key") or "").strip()
    if not key:
        raise ValueError("皮肤名不能为空")
    action = payload.get("action")
    if action == "add" and key not in items:
        items.append(key)
    elif action == "remove":
        items = [x for x in items if x != key]
    else:
        raise ValueError("未知操作: %s" % action)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1)
    return {"ok": True, "onsale": items}


def _skin_note(payload):
    key = (payload.get("key") or "").strip()
    verdict = (payload.get("verdict") or "").strip()
    if not key:
        raise ValueError("皮肤名不能为空")
    if verdict and verdict not in VERDICTS:
        raise ValueError("状态取值不合法: %s" % verdict)
    notes = rules.set_user_note(key, verdict, reason=payload.get("reason") or "")
    return {"ok": True, "skin_notes": notes}


def _target_file(profile):
    return os.path.join(OUTPUT_DIR, "%s.html" % profile["name"])


def _resolve_source(f, source):
    """source=auto 时自动挑: 有离线数据用离线数据, 否则用示例数据预览。"""
    if source in (None, "", "auto"):
        return "dump" if os.path.isdir(os.path.join(DUMPS_DIR, f["name"])) else "demo"
    return source


def _build_report(payload):
    """生成报告数据结构(不落盘)。总控台内嵌与导出报告共用这一份逻辑。

    返回 (rep, friend_archive, source, extra_desc)
    """
    store = profiles.Store()
    f = store.require(payload.get("key"))
    source = _resolve_source(f, payload.get("source"))
    onsale = pipeline.load_onsale()
    extra = ""

    if source == "dump":
        path = os.path.join(DUMPS_DIR, f["name"])
        if not os.path.isdir(path):
            raise ValueError("dumps/%s 里没有离线数据,先用 "
                             "python3 -m gifttool --ck ... --profile %s --save-dump 抓一次"
                             % (f["name"], f["name"]))
        skin_info, hero_resp, friend = cli.load_imported(path)
        if not skin_info or "heroSkinConfList" not in skin_info:
            raise ValueError("dumps/%s/skin_info.json 里没有 heroSkinConfList" % f["name"])
        rep = pipeline.build_report(friend or {"name": f["name"]}, skin_info, hero_resp,
                                    top_n=10, onsale=onsale, profile=f)
        rep["summary"]["profile_name"] = f["name"]
        rep["summary"]["profile_role"] = f.get("role") or ""
    elif source == "ck":
        ck = (payload.get("ck") or "").strip()
        if not ck:
            raise ValueError("需要填 CK(userId&&token)")
        if not f.get("camp_id"):
            raise ValueError("这个档案还没填营地ID")
        client = cli.camp.CampClient(ck=ck)
        roles = client.resolve_roles(f["camp_id"])
        friend = cli._pick_role(roles)
        if not friend["roleId"]:
            raise ValueError("没能解析出角色,营地ID 是否正确?")
        skin_info = cli._unwrap(client.get_skin_info(f["camp_id"]))
        if "heroSkinConfList" not in skin_info:
            raise ValueError("皮肤接口响应异常(可能营地又升了加密),请换 CK 重试")
        try:
            hero_resp = cli._unwrap(client.get_profile_hero_list(f["camp_id"], friend["roleId"]))
        except cli.camp.CampError:
            hero_resp = {}
        rep = pipeline.build_report(friend, skin_info, hero_resp,
                                    top_n=10, onsale=onsale, profile=f)
        rep["summary"]["profile_name"] = f["name"]
        rep["summary"]["profile_role"] = f.get("role") or ""
        # 顺手留档,以后可离线复跑
        cli._dump(skin_info, "skin_info.json", f["name"])
        cli._dump(hero_resp, "profile_hero.json", f["name"])
        cli._dump(friend, "friend.json", f["name"])
        extra = "(已同时留档到 dumps/%s/)" % f["name"]
    else:
        source = "demo"
        rep = demo_data.demo_report(top_n=10, profile=f)
        rep["summary"]["profile_name"] = f["name"]
        rep["summary"]["profile_role"] = f.get("role") or ""
        rep["summary"]["friend"] = dict(demo_data.DEMO_FRIEND, name=f["name"])
        extra = "(示例数据,只用来预览页面效果)"

    return rep, f, source, extra


def _report_blocks(payload):
    """总控台内嵌用: 直接返回内容块 HTML。

    不写文件、不记运行历史 —— 每打开一次页面就记一笔会把追踪快照搞乱。
    """
    rep, f, source, extra = _build_report(payload)
    s = rep["summary"]
    return {
        "ok": True,
        "html": report.blocks(rep),
        "source": source,
        "note": extra,
        "summary": {
            "giftable": s["giftable_total"], "on_return": s["on_return_total"],
            "not_giftable": s["not_giftable_total"], "unknown": s["unknown_total"],
            "owned": s.get("owned", ""), "missing": s.get("missing_total", 0),
            "next_return": s.get("next_return"),
            "alerts": len(rep.get("alerts") or []),
        },
    }


def _gen_report(payload):
    """导出成独立的 HTML 文件(发给别人/存档用)。"""
    store = profiles.Store()
    rep, f, source, extra = _build_report(payload)

    out = _target_file(f)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(report.render(rep))

    if source != "demo":
        watch = rep.get("watch") or {}
        snapshot = dict(watch.get("snapshot") or {})
        snapshot["__hero_missing__"] = watch.get("hero_missing") or {}
        store.record_run(f, rep["summary"], snapshot)

    return {
        "ok": True,
        "url": "/output/" + urllib.parse.quote("%s.html" % f["name"]),
        "desc": "共 %d 款可送 / %d 款待返场%s"
                % (rep["summary"]["giftable_total"], rep["summary"]["on_return_total"], extra),
    }


def _watch_date(payload):
    """给某款关注皮肤登记/清除返场日期(顶部倒计时卡片靠它)。"""
    store = profiles.Store()
    f = store.require(payload.get("key"))
    t = store.set_watch_skin_date(f, payload.get("skin_key"), payload.get("date"),
                                  announced=bool(payload.get("announced")))
    if t is None:
        raise ValueError("这个皮肤不在关注列表里,先加进来")
    return {"ok": True, "key": t.get("key"),
            "return_date": t.get("return_date") or "",
            "announced": bool(t.get("announced"))}


ROUTES = {
    "friend/save": _friend_save,
    "friend/delete": _friend_delete,
    "friend/note": _friend_note,
    "friend/note/remove": _friend_note_remove,
    "friend/watch": _friend_watch,
    "onsale": _onsale,
    "skin-note": _skin_note,
    "report": _gen_report,
    "report/blocks": _report_blocks,
    "watch/date": _watch_date,
}


# ---------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "gift-tool"

    def log_message(self, fmt, *args):
        pass  # 保持终端干净

    # ---------- 工具 ----------

    def _cors(self):
        # 报告页可能是 file:// 打开的,允许它跨源调本地接口写备注
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _text(self, text, ctype="text/html; charset=utf-8", code=200):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _payload(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError:
            return {}

    # ---------- OPTIONS(跨源预检) ----------

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---------- GET ----------

    def do_GET(self):
        path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
        if path == "/":
            self._text(PAGE)
            return
        if path == "/api/state":
            self._json(_state())
            return
        if path.startswith("/output/"):
            name = os.path.basename(path[len("/output/"):])
            full = os.path.join(OUTPUT_DIR, name)
            if os.path.isfile(full):
                with open(full, "rb") as fh:
                    body = fh.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self._cors()
                self.end_headers()
                self.wfile.write(body)
            else:
                self._text("<h3>报告不存在,先在管理页面点「生成报告」</h3>", code=404)
            return
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        self._text("<h3>404</h3>", code=404)

    # ---------- POST ----------

    def do_POST(self):
        path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
        if not path.startswith("/api/"):
            self._json({"ok": False, "error": "未知接口"}, 404)
            return
        name = path[len("/api/"):]
        handler = ROUTES.get(name)
        if not handler:
            self._json({"ok": False, "error": "未知接口: %s" % name}, 404)
            return
        try:
            result = handler(self._payload())
        except KeyError as e:
            self._json({"ok": False, "error": str(e.args[0])}, 400)
        except ValueError as e:
            self._json({"ok": False, "error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001 - 兜底,把错误回给页面而不是崩掉
            self._json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 500)
        else:
            result.setdefault("ok", True)
            result["state"] = _state()
            self._json(result)


def serve(host="127.0.0.1", port=8765, open_browser=True):
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = "http://%s:%d/" % (host, port)
    print("档案管理页面已启动: %s" % url)
    print("按 Ctrl+C 停止。数据全部写在本机 data/ 目录,不上传任何云端。")
    if open_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()


PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>王者送礼助手 · 档案管理</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #FAFAF7; color: #2C2C2A; margin: 0; font-size: 13px; }
  header { padding: 14px 24px; border-bottom: 0.5px solid #D3D1C7; background: #FFFFFF;
           display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
  h1 { font-size: 16px; font-weight: 500; margin: 0; }
  .sub { color: #888780; font-size: 12px; }
  .grow { margin-left: auto; }
  .hintbar { background: #FFF9E8; border-bottom: 0.5px solid #EF9F27; color: #633806;
             padding: 10px 24px; font-size: 12.5px; line-height: 1.8; }
  .hintbar b { color: #27500A; }
  main { display: flex; gap: 16px; padding: 16px 24px 80px; align-items: flex-start; }
  aside { width: 262px; flex: none; position: sticky; top: 16px; }
  section.detail { flex: 1; min-width: 0; }
  .panel { background: #FFFFFF; border: 0.5px solid #D3D1C7; border-radius: 12px;
           padding: 14px 16px; margin-bottom: 12px; }
  .panel h2 { font-size: 13.5px; font-weight: 500; margin: 0 0 10px; color: #2C2C2A; }
  .panel h2 .tip { font-weight: 400; color: #888780; font-size: 12px; margin-left: 6px; }
  .panel.write { background: #FBFAF4; border-color: #97C459; box-shadow: 0 1px 0 #EAF3DE; }
  .panel.write h2 { color: #27500A; font-size: 14.5px; }
  .flash { animation: fl 1.1s ease-out; }
  @keyframes fl { 0% { background: #FFF3C4; } 100% { background: #FFFFFF; } }
  .fitem { border-radius: 10px; margin-bottom: 6px; border: 0.5px solid transparent; }
  .fitem:hover { background: #F1EFE8; }
  .fitem.on { background: #E6F1FB; border-color: #85B7EB; }
  .ftop { display: flex; align-items: center; gap: 7px; padding: 8px 10px; cursor: pointer; }
  .ftop .caret { color: #888780; font-size: 11px; width: 10px; flex: none; }
  .ftop .fn { font-weight: 500; }
  .ftop .fmeta { margin-left: auto; color: #888780; font-size: 11px; }
  .fsub { padding: 0 10px 8px 27px; }
  .fsubitem { font-size: 12px; color: #5F5E5A; padding: 4px 6px; border-radius: 7px; cursor: pointer; }
  .fsubitem:hover { background: #FFFFFF; color: #0C447C; }
  input[type=text], textarea, select { width: 100%; font-family: inherit; font-size: 13px;
        border: 0.5px solid #D3D1C7; border-radius: 8px; padding: 7px 10px;
        background: #FFFFFF; color: #2C2C2A; }
  textarea { min-height: 66px; resize: vertical; line-height: 1.6; }
  input:focus, textarea:focus, select:focus { outline: none; border-color: #85B7EB; }
  label.f { display: block; color: #5F5E5A; font-size: 12px; margin: 8px 0 3px; }
  .row { display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap; }
  .row > div { flex: 1; min-width: 120px; }
  button { font-family: inherit; font-size: 12.5px; border-radius: 8px; cursor: pointer;
           border: 0.5px solid #85B7EB; background: #E6F1FB; color: #0C447C; padding: 7px 13px; }
  button:hover { border-color: #378ADD; }
  button.primary { background: #EAF3DE; border-color: #97C459; color: #27500A; }
  button.primary:hover { border-color: #6E9B2E; }
  button.ghost { background: #FFFFFF; border-color: #D3D1C7; color: #5F5E5A; }
  button.danger { background: #FCEBEB; border-color: #F09595; color: #A32D2D; }
  button.mini { padding: 3px 9px; font-size: 11.5px; border-radius: 7px; }
  button.on { background: #0C447C; color: #FFFFFF; border-color: #0C447C; }
  .chips { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; font-size: 12px;
          background: #EAF3DE; border: 0.5px solid #97C459; color: #27500A;
          border-radius: 10px; padding: 2px 9px; }
  .chip.skin { background: #FAEEDA; border-color: #EF9F27; color: #633806; }
  .chip.bad { background: #F1EFE8; border-color: #D3D1C7; color: #5F5E5A; }
  .chip b { font-weight: 500; }
  .chip .x { cursor: pointer; color: inherit; opacity: .6; }
  .chip .x:hover { opacity: 1; }
  .empty { color: #888780; font-size: 12px; }
  .timeline .note { border-left: 2px solid #D3D1C7; padding: 2px 0 2px 12px; margin-bottom: 10px; }
  .timeline .at { font-size: 11px; color: #888780; }
  .timeline .tx { margin: 2px 0 4px; line-height: 1.6; }
  .tag { font-size: 11px; border-radius: 9px; padding: 1px 7px; margin-right: 5px;
         display: inline-block; background: #E6F1FB; border: 0.5px solid #85B7EB; color: #0C447C; }
  .tag.skin { background: #FAEEDA; border-color: #EF9F27; color: #633806; }
  .wrow { border-top: 0.5px solid #F1EFE8; padding: 8px 0; }
  .wrow:first-child { border-top: none; }
  .wrow .wn { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .wrow .wn b { font-weight: 500; }
  .wrow .acts { margin-left: auto; display: flex; gap: 4px; flex-wrap: wrap; }
  .wrow .src { color: #888780; font-size: 11px; }
  .msg { font-size: 12px; color: #5F5E5A; }
  .ok { color: #27500A; }
  .bad { color: #A32D2D; }
  .toast { position: fixed; left: 50%; transform: translateX(-50%); bottom: 24px;
           background: #2C2C2A; color: #FFFFFF; padding: 10px 18px; border-radius: 10px;
           font-size: 13px; opacity: 0; transition: opacity .2s; pointer-events: none;
           max-width: 80vw; }
  .toast.show { opacity: 1; }
  .hint { color: #888780; font-size: 12px; line-height: 1.7; }
  .kv { color: #5F5E5A; font-size: 12px; }
  datalist { display: none; }
  .modal { position: fixed; inset: 0; background: rgba(44,44,42,.35); display: none;
           align-items: flex-start; justify-content: center; padding-top: 8vh; z-index: 50; }
  .modal.show { display: flex; }
  .mbox { background: #FFFFFF; border-radius: 14px; padding: 20px 22px; width: 440px;
          max-width: 92vw; box-shadow: 0 8px 32px rgba(0,0,0,.16); }
  .mbox h3 { margin: 0 0 12px; font-size: 15px; font-weight: 500; }
  .mbox .mrow { display: flex; gap: 10px; align-items: center; margin-top: 16px; }
  .reportview { padding: 14px 16px 16px; }
  .reportview .cards { margin-top: 4px; }
  input[type=date] { font-family: inherit; font-size: 12.5px; width: auto;
        border: 0.5px solid #D3D1C7; border-radius: 7px; padding: 3px 7px;
        background: #FFFFFF; color: #2C2C2A; }
  /*__REPORT_CSS__*/
</style>
</head>
<body>
<header>
  <h1>王者送礼助手</h1>
  <span class="sub">一个页面搞定:建档 · 写备注 · 看该送什么 · 追踪返场倒计时 —— 全部存在你本机 data/friends.json</span>
  <span class="grow"></span>
  <button id="newFriend" class="primary">+ 新建朋友档案</button>
</header>
<div class="hintbar">
  <b>整个工具就这一页。</b>
  ① 右上角「新建朋友档案」给一个朋友建档 &nbsp;→&nbsp;
  ② 左边点他,在<b>最上面那个绿框里写备注</b>(想到什么写什么) &nbsp;→&nbsp;
  ③ 下面的「送礼分析」直接告诉你该送什么、有没有快到期的返场。<br>
  <b>想看某个朋友的子档案?</b>左边点他名字前面的小三角 ▸,展开「备注 / 关注英雄 / 关注皮肤 / 分析」。
  <b>想给某个皮肤加上返场倒计时?</b>在「关注的皮肤」里给它填个返场日期就行。
</div>
<main>
  <aside>
    <div class="panel">
      <h2>朋友档案 <span class="tip" id="fcount"></span></h2>
      <input type="text" id="filter" placeholder="输入名字筛选…" style="margin-bottom:8px;">
      <div id="flist"></div>
    </div>
  </aside>
  <section class="detail" id="detail"></section>
</main>
<div class="toast" id="toast"></div>

<div class="modal" id="newModal">
  <div class="mbox">
    <h3>新建朋友档案</h3>
    <label class="f">备注名(你认得就行)</label>
    <input type="text" id="nm_name" placeholder="如 老王、大学室友">
    <label class="f">他的营地ID(可以留空,以后补)</label>
    <input type="text" id="nm_camp" placeholder="王者营地里的那个数字ID">
    <label class="f">区服 / 系统(决定能不能送: iOS 和安卓不能互赠)</label>
    <input type="text" id="nm_role" placeholder="如 微信区·安卓">
    <label class="f">顺手写一句备注(可留空)</label>
    <textarea id="nm_note" placeholder="例:开黑时他说本命是公孙离"></textarea>
    <div class="mrow">
      <button class="primary" id="nm_ok">建立这个档案</button>
      <button class="ghost" id="nm_cancel">取消</button>
      <span class="msg" id="nm_msg"></span>
    </div>
  </div>
</div>

<datalist id="heroOptions"></datalist>
<datalist id="skinOptions"></datalist>
<script>
var S = { state: null, cur: null, expanded: {} };

function toast(msg) {
  var t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast show";
  clearTimeout(t._h);
  t._h = setTimeout(function () { t.className = "toast"; }, 2600);
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
  });
}

function api(path, body) {
  return fetch("/api/" + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {})
  }).then(function (r) { return r.json(); }).then(function (j) {
    if (j.state) { S.state = j.state; }
    if (!j.ok) { toast("✗ " + (j.error || "操作失败")); throw new Error(j.error); }
    return j;
  });
}

function findFriend(name) {
  var fs = (S.state && S.state.friends) || [];
  for (var i = 0; i < fs.length; i++) { if (fs[i].name === name) return fs[i]; }
  return null;
}

function load() {
  return fetch("/api/state").then(function (r) { return r.json(); }).then(function (st) {
    S.state = st;
    var ho = document.getElementById("heroOptions"), so = document.getElementById("skinOptions");
    ho.innerHTML = ""; so.innerHTML = "";
    st.heroes.forEach(function (h) {
      ho.insertAdjacentHTML("beforeend", '<option value="' + esc(h.name) + '">');
      h.skins.forEach(function (k) {
        so.insertAdjacentHTML("beforeend", '<option value="' + esc(k) + '">');
      });
    });
    if (!S.cur && st.friends.length) { S.cur = st.friends[0].name; }
    if (S.cur && !findFriend(S.cur)) { S.cur = st.friends.length ? st.friends[0].name : null; }
    renderList();
    renderDetail();
  });
}

function reload(opts) {
  opts = opts || {};
  var y = window.scrollY;
  return load().then(function () {
    if (opts.keepScroll !== false) { window.scrollTo(0, y); }
    if (opts.jump) { jumpTo(opts.jump); }
  });
}

function applyFilter() {
  var q = (document.getElementById("filter").value || "").trim();
  Array.prototype.forEach.call(document.querySelectorAll("#flist .fitem"), function (el) {
    var nm = el.getAttribute("data-name") || "", meta = el.getAttribute("data-meta") || "";
    el.style.display = (!q || nm.indexOf(q) >= 0 || meta.indexOf(q) >= 0) ? "" : "none";
  });
}

function renderList() {
  var fs = S.state.friends || [];
  document.getElementById("fcount").textContent = fs.length ? "( " + fs.length + " 位 )" : "";
  var box = document.getElementById("flist");
  if (!fs.length) {
    box.innerHTML = '<div class="empty">还没有档案。<br>点右上角「新建朋友档案」开始,'
      + '先填个你认得的备注名就行,营地ID可以以后补。</div>';
    return;
  }
  box.innerHTML = fs.map(function (f) {
    var on = f.name === S.cur ? " on" : "";
    var open = !!S.expanded[f.name];
    var noteN = (f.notes || []).length, heroN = (f.watch_heroes || []).length;
    var skinN = (f.watch_skins || []).length;
    var meta = (f.camp_id ? "ID " + f.camp_id : "无ID") + " · 备注" + noteN;
    return '<div class="fitem' + on + '" data-name="' + esc(f.name) + '" data-meta="'
      + esc((f.camp_id || "") + " " + (f.role || "")) + '">'
      + '<div class="ftop" data-open="' + esc(f.name) + '">'
      + '<span class="caret">' + (open ? "▾" : "▸") + '</span>'
      + '<span class="fn">' + esc(f.name) + '</span>'
      + '<span class="fmeta">' + esc(meta) + '</span></div>'
      + '<div class="fsub"' + (open ? "" : ' style="display:none;"') + '>'
      + '<div class="fsubitem" data-jump="' + esc(f.name) + '|notes">✍️ 备注 ' + noteN + ' 条</div>'
      + '<div class="fsubitem" data-jump="' + esc(f.name) + '|heroes">🦸 关注英雄 ' + heroN + '</div>'
      + '<div class="fsubitem" data-jump="' + esc(f.name) + '|skins">🎁 关注皮肤 ' + skinN + '</div>'
      + '<div class="fsubitem" data-jump="' + esc(f.name) + '|report">📊 送礼分析</div>'
      + '</div></div>';
  }).join("");
  applyFilter();
}

function toggleFriend(name) {
  if (S.cur === name) { S.expanded[name] = !S.expanded[name]; }
  else { S.cur = name; S.expanded[name] = true; }
  renderList();
  renderDetail();
}

function jumpTo(key) {
  var map = { notes: "panel-notes", heroes: "panel-heroes",
              skins: "panel-skins", report: "panel-reportview" };
  var el = document.getElementById(map[key] || key);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  el.classList.remove("flash");
  void el.offsetWidth;
  el.classList.add("flash");
}

function renderDetail() {
  var box = document.getElementById("detail");
  var f = S.cur ? findFriend(S.cur) : null;
  if (!f) {
    box.innerHTML = '<div class="panel"><h2>还没有选中朋友</h2><div class="hint">'
      + '左边点一个朋友,或点右上角「新建朋友档案」。</div></div>';
    return;
  }
  var h = [];

  // 1) 写备注 —— 放最上面,最显眼
  h.push('<div class="panel write" id="panel-notes">'
    + '<h2>✍️ 写备注 · 就在下面的框里输入 <span class="tip">写给「' + esc(f.name)
    + '」,英雄名/皮肤名会自动认出来并加入关注</span></h2>'
    + '<textarea id="noteText" placeholder="例:今天开黑他说其实也挺喜欢公孙离的,'
    + '可惜当年没买到祈雪灵祝"></textarea>'
    + '<div class="row" style="margin-top:8px;">'
    + '<div style="flex:none;"><button class="primary" id="addNote">保存这条备注</button></div>'
    + '<span class="msg" id="noteMsg">保存后会立刻解析出英雄/皮肤,并出现在下面</span>'
    + '</div></div>');

  // 2) 送礼分析 —— 报告内容直接嵌在这一页里,不用再开别的文件
  h.push('<div class="panel reportview" id="panel-reportview">'
    + '<h2>📊 送礼分析 <span class="tip" id="repSrc">正在生成…</span></h2>'
    + '<div id="repBox"><div class="hint">正在生成分析…</div></div>'
    + '<div class="row" style="margin-top:12px;">'
    + '<div style="flex:none;"><button id="reloadRep">重新生成分析</button></div>'
    + '<div style="flex:none;"><button class="ghost" id="openRep">另存为报告文件</button></div>'
    + '<span class="msg" id="repMsg"></span></div></div>');

  // 3) 这个朋友是谁
  h.push('<div class="panel" id="panel-who"><h2>这个朋友是谁</h2><div class="row">'
    + '<div><label class="f">你给他起的备注名</label>'
    + '<input type="text" id="f_name" value="' + esc(f.name) + '"></div>'
    + '<div><label class="f">他的营地ID(可后补)</label>'
    + '<input type="text" id="f_camp" value="' + esc(f.camp_id || "") + '"></div>'
    + '<div><label class="f">区服 / 系统(决定能不能送)</label>'
    + '<input type="text" id="f_role" value="' + esc(f.role || "") + '" placeholder="如 微信区·安卓"></div>'
    + '</div><div class="row" style="margin-top:10px;">'
    + '<div style="flex:none;"><button class="primary" id="saveF">保存资料</button></div>'
    + '<div style="flex:none;"><button class="danger" id="delF">删除这个档案</button></div>'
    + '<div class="kv" style="align-self:center;">建立于 ' + esc(f.created_at || "-")
    + ' · 最后改动 ' + esc(f.updated_at || "-") + '</div></div></div>');

  // 4) 关注英雄
  h.push('<div class="panel" id="panel-heroes"><h2>关注英雄 <span class="tip">'
    + '这些人的皮肤都会被纳入分析(备注里认出来的会自动进来)</span></h2>'
    + '<div class="chips" id="heroChips"></div>'
    + '<div class="row"><div><input type="text" id="heroInput" list="heroOptions" '
    + 'placeholder="输入英雄名,如 公孙离"></div>'
    + '<div style="flex:none;"><button id="addHero">添加</button></div></div></div>');

  // 5) 关注的皮肤(带返场日期 → 顶部倒计时)
  h.push('<div class="panel" id="panel-skins"><h2>关注的皮肤 <span class="tip">'
    + '会持续追踪返场窗口;给它填个返场日期,上面的倒计时就会动起来</span></h2>'
    + '<div id="skinRows"></div>'
    + '<div class="row" style="margin-top:10px;"><div>'
    + '<input type="text" id="skinInput" list="skinOptions" '
    + 'placeholder="输入皮肤名,如 公孙离·祈雪灵祝"></div>'
    + '<div style="flex:none;"><button id="addSkin">添加追踪</button></div></div>'
    + '<div class="hint" style="margin-top:8px;">'
    + '① 右边四个按钮 = 给这款皮肤下人工判断,优先级最高,以后一直生效。<br>'
    + '② 「正在返场」= 它现在就在商城卖,判定立刻变成「可赠送」。<br>'
    + '③ 返场日期 = 你知道的(或官方公告的)返场日,填了就进倒计时;'
    + '每周的自动追踪任务查到公告也会帮你填。</div></div>');

  // 6) 导出报告文件
  h.push('<div class="panel" id="panel-report"><h2>另存为报告文件'
    + ' <span class="tip">分析已经在上面了,这里只是导出一份可以发出去的文件</span></h2>'
    + '<div class="hint">会写到 output/' + esc(f.name) + '.html,可以直接发给朋友或存档。</div>'
    + '<div class="row" style="margin-top:10px;">'
    + '<div><label class="f">数据来源</label>'
    + '<select id="src">'
    + '<option value="auto">自动(有离线数据就用离线数据)</option>'
    + '<option value="demo">示例数据(先看效果)</option>'
    + '<option value="dump">离线数据 dumps/' + esc(f.name) + '/</option>'
    + '<option value="ck">用 CK 现场抓</option></select></div>'
    + '<div><label class="f">CK(选「用 CK 现场抓」才需要填)</label>'
    + '<input type="text" id="ck" placeholder="userId&&token,务必用小号"></div>'
    + '<div style="flex:none;"><button class="primary" id="gen">导出报告文件</button></div>'
    + '</div><div id="genOut" class="kv" style="margin-top:10px;"></div></div>');

  // 7) 备注时间线
  var notes = (f.notes || []).slice().reverse();
  h.push('<div class="panel"><h2>备注时间线 <span class="tip">共 ' + (f.notes || []).length
    + ' 条</span></h2><div class="timeline" id="timeline">');
  if (!notes.length) {
    h.push('<div class="empty">还没有备注,在上面那个框里写一条试试。</div>');
  } else {
    notes.forEach(function (n, i) {
      var tags = "";
      (n.parsed_heroes || []).forEach(function (x) {
        tags += '<span class="tag">英雄 ' + esc(x) + '</span>';
      });
      (n.parsed_skins || []).forEach(function (k) {
        tags += '<span class="tag skin">皮肤 ' + esc(k) + '</span>';
      });
      h.push('<div class="note"><div class="at">' + esc(n.at) + '</div>'
        + '<div class="tx">' + esc(n.text) + '</div>'
        + '<div>' + (tags || '<span class="empty">没识别到英雄/皮肤</span>')
        + '<button class="mini ghost" data-rmnote="'
        + ((f.notes || []).length - 1 - i) + '" style="margin-left:6px;">删掉这条</button>'
        + '</div></div>');
    });
  }
  h.push('</div></div>');

  // 7) 全局
  h.push('<div class="panel"><h2>全局设置</h2>'
    + '<div class="kv">当前在售/返场名单:' + (S.state.onsale.length
      ? S.state.onsale.map(function (k) {
          return '<span class="chip">' + esc(k)
            + ' <span class="x" data-onsale="' + esc(k) + '">×</span></span>';
        }).join(" ")
      : '<span class="empty">空(有皮肤商城在售/返场时在这里记录,判定就会变成「可赠送」)</span>')
    + '</div>'
    + '<div class="kv" style="margin-top:8px;">你标注过的皮肤:'
    + (Object.keys(S.state.skin_notes || {}).length
      ? Object.keys(S.state.skin_notes).map(function (k) {
          return '<span class="chip bad">' + esc(k) + " → "
            + esc(S.state.skin_notes[k].gift) + ' <span class="x" data-note="'
            + esc(k) + '">×</span></span>';
        }).join(" ")
      : '<span class="empty">还没有(在关注皮肤右边点按钮就会出现在这里)</span>')
    + '</div></div>');

  box.innerHTML = h.join("");
  renderChips(f);
  bindWidgets(f);
  loadReport(f);
}

// ---- 送礼分析: 报告内容直接嵌在本页 ----
var SRC_LABEL = { demo: "示例数据", dump: "离线数据", ck: "现场 CK 抓取" };

function loadReport(f, src) {
  var box = document.getElementById("repBox");
  if (!box) return;
  box.innerHTML = '<div class="hint">正在生成分析…</div>';
  var label = document.getElementById("repSrc");
  if (label) label.textContent = "正在生成…";
  api("report/blocks", { key: f.name, source: src || "auto" }).then(function (j) {
    box.innerHTML = j.html;
    if (label) {
      label.textContent = "数据来源:" + (SRC_LABEL[j.source] || j.source)
        + (j.source === "dump" ? " dumps/" + f.name : "")
        + (j.note ? " " + j.note : "");
    }
  }).catch(function (e) {
    box.innerHTML = '<div class="msg bad">分析生成失败:' + esc(String(e.message || e))
      + '<br>把「数据来源」换成「示例数据」再点「重新生成分析」就能先看效果。</div>';
    if (label) label.textContent = "生成失败";
  });
}

function renderChips(f) {
  var box = document.getElementById("heroChips");
  var hs = f.watch_heroes || [];
  box.innerHTML = hs.length ? hs.map(function (h) {
    return '<span class="chip"><b>' + esc(h.name) + '</b>'
      + '<span class="x" data-rmhero="' + esc(h.name) + '">×</span></span>';
  }).join("") : '<span class="empty">还没有关注英雄</span>';

  var rows = document.getElementById("skinRows");
  var ss = f.watch_skins || [];
  if (!ss.length) {
    rows.innerHTML = '<div class="empty">还没有关注皮肤</div>';
  } else {
    rows.innerHTML = ss.map(function (s) {
      var key = s.key || (s.hero + "·" + s.skin);
      var mine = (S.state.skin_notes || {})[key];
      var inSale = S.state.onsale.indexOf(key) >= 0;
      var acts = S.state.verdicts.map(function (v) {
        var on = mine && mine.gift === v ? " on" : "";
        return '<button class="mini' + on + '" data-note="' + esc(key)
          + '" data-verdict="' + esc(v) + '">' + esc(v) + '</button>';
      }).join("");
      acts += '<button class="mini' + (inSale ? " on" : "") + '" data-onsale="'
        + esc(key) + '" data-actsale="1">正在返场</button>';
      var rd = s.return_date || "";
      var dl = "";
      if (rd) {
        var t = new Date(rd + "T00:00:00");
        var now = new Date(S.state.today + "T00:00:00");
        var n = Math.round((t - now) / 86400000);
        dl = n >= 0 ? '<span class="tag' + (n <= 7 ? " skin" : "")
            + '">还剩 ' + n + ' 天</span>' : '<span class="tag">已过 ' + Math.abs(n) + ' 天</span>';
      }
      return '<div class="wrow"><div class="wn"><b>' + esc(key) + '</b>'
        + (mine ? '<span class="tag">已标注:' + esc(mine.gift) + '</span>' : '')
        + '<span class="src">' + esc(s.source || "") + '</span>'
        + '<span class="acts">' + acts
        + '<button class="mini danger" data-rmskin="' + esc(key) + '">移除</button></span>'
        + '</div>'
        + '<div class="wn" style="margin-top:7px;">'
        + '<span class="src">返场日期</span>'
        + '<input type="date" data-retdate="' + esc(key) + '" value="' + esc(rd) + '">'
        + (rd ? '<button class="mini' + (s.announced ? " on" : "") + '" data-announced="'
                + esc(key) + '">官方已公告</button>' : '')
        + (rd ? '<span class="src">← 上面倒计时卡片用的就是它</span>' : '')
        + '<button class="mini ghost" data-retclear="' + esc(key) + '"'
        + (rd ? '' : ' style="display:none;"') + '>清空日期</button>'
        + dl
        + '</div></div>';
    }).join("");
  }
}

function bindWidgets(f) {
  function noteMsg(t, good) {
    var el = document.getElementById("noteMsg");
    el.textContent = t;
    el.className = "msg " + (good ? "ok" : "bad");
  }
  document.getElementById("saveF").onclick = function () {
    api("friend/save", {
      orig_name: f.name,
      name: document.getElementById("f_name").value,
      camp_id: document.getElementById("f_camp").value,
      role: document.getElementById("f_role").value
    }).then(function (j) { S.cur = j.name; S.expanded[j.name] = true;
      toast("已保存"); reload(); });
  };
  document.getElementById("delF").onclick = function () {
    if (!confirm("确定删除档案「" + f.name + "」?备注和关注列表会一起删掉。")) return;
    api("friend/delete", { key: f.name }).then(function () {
      S.cur = null; toast("已删除"); reload({ keepScroll: false });
    });
  };
  document.getElementById("addNote").onclick = function () {
    var ta = document.getElementById("noteText");
    if (!ta.value.trim()) { noteMsg("先写点什么再保存"); ta.focus(); return; }
    noteMsg("正在保存…", true);
    api("friend/note", { key: f.name, text: ta.value }).then(function (j) {
      var parts = [];
      if (j.heroes && j.heroes.length) parts.push("英雄 " + j.heroes.join("、"));
      if (j.skins && j.skins.length) parts.push("皮肤 " + j.skins.join("、"));
      toast(parts.length ? "已记录,并识别出:" + parts.join(" / ") : "已记录(没识别到英雄)");
      reload({ keepScroll: false });
    }).catch(function () { noteMsg("保存失败,看下方提示", false); });
  };
  document.getElementById("addHero").onclick = function () {
    var v = document.getElementById("heroInput").value.trim();
    if (!v) return;
    api("friend/watch", { key: f.name, add_heroes: [v] }).then(function (j) {
      if (j.problems && j.problems.length) { toast("✗ " + j.problems.join(";")); return; }
      toast("已关注 " + v); reload();
    });
  };
  document.getElementById("addSkin").onclick = function () {
    var v = document.getElementById("skinInput").value.trim();
    if (!v) return;
    api("friend/watch", { key: f.name, add_skins: [v] }).then(function (j) {
      if (j.problems && j.problems.length) { toast("✗ " + j.problems.join(";")); return; }
      toast("已加入追踪 " + v); reload();
    });
  };
  document.getElementById("gen").onclick = function () {
    var out = document.getElementById("genOut");
    out.textContent = "正在生成…";
    api("report", {
      key: f.name,
      source: document.getElementById("src").value,
      ck: document.getElementById("ck").value
    }).then(function (j) {
      out.innerHTML = j.desc + ' · <a href="' + j.url + '" target="_blank">打开这份文件</a>';
      window.open(j.url, "_blank");
      reload();
    }).catch(function () { out.textContent = "生成失败,看上面的提示"; });
  };
  document.getElementById("reloadRep").onclick = function () {
    loadReport(f, document.getElementById("src") ? document.getElementById("src").value : "auto");
  };
  document.getElementById("openRep").onclick = function () {
    window.open("/output/" + encodeURIComponent(f.name + ".html"), "_blank");
  };
}

// 统一事件委托,避免每次重建后重复绑定
document.addEventListener("click", function (e) {
  var el = e.target.closest ? e.target.closest(
    "[data-open],[data-jump],[data-rmhero],[data-rmskin],[data-verdict],"
    + "[data-actsale],[data-rmnote],[data-announced],[data-retclear]") : null;
  if (!el) return;
  var f = S.cur ? findFriend(S.cur) : null;

  if (el.hasAttribute("data-open")) {
    toggleFriend(el.getAttribute("data-open"));
    return;
  }
  if (el.hasAttribute("data-jump")) {
    var parts = el.getAttribute("data-jump").split("|");
    S.cur = parts[0];
    S.expanded[parts[0]] = true;
    renderList();
    renderDetail();
    jumpTo(parts[1]);
    return;
  }
  if (!f) return;

  if (el.hasAttribute("data-announced")) {
    var akey = el.getAttribute("data-announced");
    var rec = null;
    (f.watch_skins || []).forEach(function (x) {
      if ((x.key || (x.hero + "·" + x.skin)) === akey) rec = x;
    });
    if (!rec || !rec.return_date) { toast("先填一个返场日期"); return; }
    api("watch/date", { key: f.name, skin_key: akey, date: rec.return_date,
                        announced: !rec.announced }).then(function () {
      toast(rec.announced ? "已取消「官方已公告」标记" : "已标记为官方公告的确定日期");
      reload();
    });
    return;
  }
  if (el.hasAttribute("data-retclear")) {
    api("watch/date", { key: f.name, skin_key: el.getAttribute("data-retclear"), date: "" })
      .then(function () { toast("已清除返场日期"); reload(); });
    return;
  }
  if (el.hasAttribute("data-rmhero")) {
    api("friend/watch", { key: f.name, rm_heroes: [el.getAttribute("data-rmhero")] })
      .then(function () { toast("已移除"); reload(); });
    return;
  }
  if (el.hasAttribute("data-rmskin")) {
    api("friend/watch", { key: f.name, rm_skins: [el.getAttribute("data-rmskin")] })
      .then(function () { toast("已移除"); reload(); });
    return;
  }
  if (el.hasAttribute("data-verdict")) {
    var key = el.getAttribute("data-note"), v = el.getAttribute("data-verdict");
    var mine = (S.state.skin_notes || {})[key];
    var value = mine && mine.gift === v ? "" : v;
    api("skin-note", { key: key, verdict: value }).then(function () {
      toast(value ? "已标注为「" + value + "」" : "已取消标注"); reload();
    });
    return;
  }
  if (el.hasAttribute("data-actsale")) {
    var k2 = el.getAttribute("data-onsale");
    var on = S.state.onsale.indexOf(k2) >= 0;
    api("onsale", { action: on ? "remove" : "add", key: k2 }).then(function () {
      toast(on ? "已从在售名单移除" : "已加入在售名单(判定为可赠送)"); reload();
    });
    return;
  }
  if (el.hasAttribute("data-rmnote")) {
    api("friend/note/remove", { key: f.name, index: parseInt(el.getAttribute("data-rmnote"), 10) })
      .then(function () { toast("已删掉这条备注"); reload(); });
    return;
  }
  if (el.hasAttribute("data-onsale")) {
    api("onsale", { action: "remove", key: el.getAttribute("data-onsale") })
      .then(function () { toast("已移除"); reload(); });
    return;
  }
  if (el.hasAttribute("data-note")) {
    api("skin-note", { key: el.getAttribute("data-note"), verdict: "" })
      .then(function () { toast("已取消标注"); reload(); });
    return;
  }
});

document.getElementById("filter").oninput = applyFilter;

// 返场日期: 选完立刻存盘,顶部倒计时跟着变
document.addEventListener("change", function (e) {
  var el = e.target;
  if (!el || !el.hasAttribute || !el.hasAttribute("data-retdate")) return;
  var f = S.cur ? findFriend(S.cur) : null;
  if (!f) return;
  var v = el.value || "";
  api("watch/date", { key: f.name, skin_key: el.getAttribute("data-retdate"), date: v })
    .then(function () {
      toast(v ? "已登记返场日期 " + v + ",顶部倒计时已更新" : "已清除返场日期");
      reload();
    });
});

// ---- 新建档案(页面内表单,不再用浏览器弹窗) ----
function openNew() {
  document.getElementById("nm_name").value = "";
  document.getElementById("nm_camp").value = "";
  document.getElementById("nm_role").value = "";
  document.getElementById("nm_note").value = "";
  document.getElementById("nm_msg").textContent = "";
  document.getElementById("newModal").classList.add("show");
  setTimeout(function () { document.getElementById("nm_name").focus(); }, 30);
}
function closeNew() { document.getElementById("newModal").classList.remove("show"); }

document.getElementById("newFriend").onclick = openNew;
document.getElementById("nm_cancel").onclick = closeNew;
document.getElementById("newModal").onclick = function (e) {
  if (e.target === this) closeNew();
};
document.getElementById("nm_ok").onclick = function () {
  var name = document.getElementById("nm_name").value.trim();
  var msg = document.getElementById("nm_msg");
  if (!name) { msg.textContent = "备注名不能为空"; return; }
  msg.textContent = "正在建立…";
  api("friend/save", {
    name: name,
    camp_id: document.getElementById("nm_camp").value,
    role: document.getElementById("nm_role").value,
    note: document.getElementById("nm_note").value
  }).then(function () {
    S.cur = name; S.expanded[name] = true;
    closeNew();
    toast("档案已建立,现在可以写备注了");
    reload({ keepScroll: false, jump: "notes" });
  }).catch(function (err) { msg.textContent = String(err.message || err); });
};

document.addEventListener("keydown", function (e) {
  if (e.key === "Escape") closeNew();
});

load();
</script>
</body>
</html>
""".replace("/*__REPORT_CSS__*/", report.REPORT_CSS)
