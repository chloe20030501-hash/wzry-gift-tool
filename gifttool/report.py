"""报告内容块 + HTML 报告生成。

两种用法:
  1. blocks(report) —— 只出「内容块」(卡片/提醒/现在就能送/关注皮肤/英雄明细)的 HTML,
     不带 <html> 外壳。本地总控台(server.py)直接把它嵌进页面里,所以
     你看的是同一个页面,不用先去开另存的报告文件。
  2. render(report) —— 完整自包含单文件,导出/发给别人用。
"""

import datetime
import html

VERDICT_COLOR = {
    "可赠送": "#3B6D11",
    "返场时可送": "#185FA5",
    "不可赠送": "#5F5E5A",
    "待确认": "#854F0B",
    "已拥有": "#5F5E5A",
}
VERDICT_BG = {
    "可赠送": "#EAF3DE",
    "返场时可送": "#E6F1FB",
    "不可赠送": "#F1EFE8",
    "待确认": "#FAEEDA",
    "已拥有": "#F1EFE8",
}
VERDICT_STROKE = {
    "可赠送": "#97C459",
    "返场时可送": "#85B7EB",
    "不可赠送": "#D3D1C7",
    "待确认": "#EF9F27",
    "已拥有": "#D3D1C7",
}

ALERT_STYLE = {
    "hot": ("#27500A", "#F4F8EC", "#97C459", "可送提醒"),
    "warn": ("#633806", "#FAEEDA", "#EF9F27", "需注意"),
    "info": ("#0C447C", "#E6F1FB", "#85B7EB", "变化"),
}


def _esc(v):
    return html.escape(str(v if v is not None else ""))


def _verdict_badge(verdict):
    color = VERDICT_COLOR.get(verdict, "#5F5E5A")
    bg = VERDICT_BG.get(verdict, "#F1EFE8")
    stroke = VERDICT_STROKE.get(verdict, "#D3D1C7")
    return ('<span style="display:inline-block;white-space:nowrap;padding:1px 8px;'
            'border-radius:10px;font-size:12px;color:%s;background:%s;'
            'border:0.5px solid %s;">%s</span>' % (color, bg, stroke, _esc(verdict)))


# ---------------------------------------------------------------
# 共享样式(总控台页面会复用,所以独立成常量)
# ---------------------------------------------------------------

REPORT_CSS = """
  .cards { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }
  .card { background: #FFFFFF; border: 0.5px solid #D3D1C7; border-radius: 12px;
          padding: 11px 14px; min-width: 108px; flex: 1; }
  .card .num { font-size: 21px; font-weight: 500; line-height: 1.25; }
  .card .lbl { font-size: 12px; color: #5F5E5A; margin-top: 2px; }
  .card .hint { font-size: 11px; color: #888780; margin-top: 3px; line-height: 1.45; }
  .card.countdown { background: #E6F1FB; border-color: #85B7EB; }
  .card.countdown.soon { background: #FCEBEB; border-color: #F09595; }
  .card.countdown .num { color: #0C447C; }
  .card.countdown.soon .num { color: #A32D2D; }
  .hintbar { background: #FFFFFF; border: 0.5px solid #D3D1C7; border-radius: 12px;
             padding: 12px 16px; font-size: 12.5px; color: #5F5E5A; line-height: 1.8;
             margin-bottom: 14px; }
  .legend { font-size: 12px; color: #5F5E5A; line-height: 2; margin-bottom: 16px; }
  .wish { background: #F4F8EC; border: 0.5px solid #97C459; border-radius: 12px;
          padding: 16px; margin-bottom: 16px; }
  .wish-head { font-size: 14px; font-weight: 500; color: #27500A; margin-bottom: 10px; }
  .alerts { background: #FFFFFF; border: 0.5px solid #D3D1C7; border-radius: 12px;
            padding: 16px; margin-bottom: 16px; }
  .alerts-head { font-size: 14px; font-weight: 500; margin-bottom: 10px; }
  .watch { background: #FFFFFF; border: 0.5px solid #D3D1C7; border-radius: 12px;
           padding: 16px; margin-bottom: 16px; }
  .watch-head { font-size: 14px; font-weight: 500; margin-bottom: 10px; color: #0C447C; }
  .hero { background: #FFFFFF; border: 0.5px solid #D3D1C7; border-radius: 12px;
          padding: 16px; margin-bottom: 14px; }
  .hero-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
  .hero-name { font-size: 16px; font-weight: 500; }
  .tag { font-size: 11px; color: #0C447C; background: #E6F1FB; border: 0.5px solid #85B7EB;
         border-radius: 10px; padding: 1px 8px; }
  .tag.hot { color: #27500A; background: #EAF3DE; border-color: #97C459; }
  .tag.skin { color: #854F0B; background: #FAEEDA; border-color: #EF9F27; }
  .meta { font-size: 12px; color: #5F5E5A; margin-left: auto; }
  .blocks table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .blocks th { text-align: left; font-weight: 500; font-size: 12px; color: #5F5E5A;
               border-bottom: 0.5px solid #D3D1C7; padding: 6px 8px; }
  .blocks td { border-bottom: 0.5px solid #F1EFE8; padding: 7px 8px; vertical-align: middle; }
  .wish table, .watch table, .hero table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .wish th, .watch th, .hero th { text-align: left; font-weight: 500; font-size: 12px;
      color: #5F5E5A; border-bottom: 0.5px solid #D3D1C7; padding: 6px 8px; }
  .wish td, .watch td, .hero td { border-bottom: 0.5px solid #F1EFE8; padding: 7px 8px;
      vertical-align: middle; }
  .soon { color: #A32D2D; font-size: 12px; }
  .cnt { color: #185FA5; font-size: 12px; }
"""


# ---------------------------------------------------------------
# 内容块
# ---------------------------------------------------------------

def _skin_row(skin):
    gift = skin["gift"]
    muted = gift["verdict"] == "不可赠送"
    name_style = ' style="color:#888780;"' if muted else ""
    price = gift["price"] or "-"
    return (
        '<tr>'
        '<td%s>%s</td>'
        '<td%s>%s</td>'
        '<td%s style="text-align:right;">%s</td>'
        '<td>%s</td>'
        '<td style="color:#5F5E5A;font-size:12px;">%s</td>'
        '</tr>'
    ) % (
        name_style, _esc(skin.get("szTitle", "")),
        name_style, _esc(gift["rarity"]),
        name_style, _esc(price),
        _verdict_badge(gift["verdict"]),
        _esc(gift["reason"]),
    )


def _card_block(report):
    s = report["summary"]
    nr = s.get("next_return") or {}
    nxt = nr.get("next")

    # 倒计时卡片:离目标清单里最近的一款返场还有几天
    if nxt:
        dl = nxt.get("days_left")
        soon = isinstance(dl, int) and 0 <= dl <= 7
        if not isinstance(dl, int):
            num = "—"
        elif dl < 0:
            num = "已过 %d 天" % abs(dl)
        elif dl == 0:
            num = "就是今天"
        else:
            num = "剩 %d 天" % dl
        extra = []
        if nxt.get("hero") or nxt.get("skin"):
            extra.append(_esc("%s·%s" % (nxt.get("hero", ""), nxt.get("skin", ""))))
        extra.append("返场日 " + _esc(nxt.get("date", "")))
        extra.append("官方已公告" if nxt.get("announced") else "手动登记")
        countdown = (
            '<div class="card countdown%s"><div class="num">%s</div>'
            '<div class="lbl">离最近的返场</div><div class="hint">%s</div></div>'
            % (" soon" if soon else "", num, " · ".join(extra)))
    else:
        countdown = (
            '<div class="card countdown"><div class="num">—</div>'
            '<div class="lbl">离最近的返场</div>'
            '<div class="hint">还没有登记返场日期。<br>在下面「关注的皮肤」里给某一款填个日期,'
            '这里就会开始倒计时。</div></div>')

    return (
        '<div class="cards">'
        '<div class="card"><div class="num">%s</div><div class="lbl">他已有的皮肤</div>'
        '<div class="hint">他账号里已有 %s 款</div></div>'
        '<div class="card"><div class="num">%d</div><div class="lbl">本次分析的英雄</div>'
        '<div class="hint">常用 ∪ 战力 ∪ 你关注的</div></div>'
        '<div class="card"><div class="num">%d</div><div class="lbl">他缺的皮肤</div>'
        '<div class="hint">只数上面这些英雄的</div></div>'
        '<div class="card"><div class="num" style="color:#3B6D11;">%d</div>'
        '<div class="lbl">现在就能送</div>'
        '<div class="hint">商城在售,今天就能送</div></div>'
        '%s'
        '</div>'
    ) % (_esc(s.get("owned", "")), _esc(s.get("owned", "")),
         s["hero_count"], s.get("missing_total", 0), s["giftable_total"], countdown)


def _wishlist_block(report):
    items = report.get("wishlist") or []
    if not items:
        return ('<div class="banner warn">当前没有「立刻就能送」的缺失皮肤: '
                '要么他的常用/战力英雄皮肤已集齐,要么缺的都属限定待返场或永久不可赠送类型。</div>')
    rows = "".join(
        '<tr><td>%s%s</td><td>%s</td><td>%s</td><td style="text-align:right;">%s 点券</td></tr>'
        % (_esc(i["hero"]),
           ' <span class="tag">关注</span>' if i.get("from_watch") else "",
           _esc(i["skin"]), _esc(i["rarity"]), _esc(i["price"] or "-"))
        for i in items
    )
    return """
<section class="wish">
  <div class="wish-head">现在就能送 · 共 %d 款</div>
  <table>
    <thead><tr><th>英雄</th><th>皮肤</th><th>品质</th><th style="text-align:right;">价格</th></tr></thead>
    <tbody>%s</tbody>
  </table>
</section>""" % (len(items), rows)


def _alert_block(report):
    alerts = report.get("alerts") or []
    if not alerts:
        return ""
    cards = []
    for a in alerts:
        color, bg, stroke, label = ALERT_STYLE.get(a["level"], ALERT_STYLE["info"])
        cards.append(
            '<div style="background:%s;border:0.5px solid %s;border-radius:10px;'
            'padding:10px 14px;margin-bottom:8px;">'
            '<span style="font-size:11px;color:%s;border:0.5px solid %s;border-radius:9px;'
            'padding:1px 7px;margin-right:8px;">%s</span>'
            '<span style="color:%s;font-size:13px;">%s</span></div>'
            % (bg, stroke, color, stroke, label, color, _esc(a["text"]))
        )
    return """
<section class="alerts">
  <div class="alerts-head">追踪提醒 · %d 条</div>
  %s
</section>""" % (len(alerts), "".join(cards))


def _watch_block(report):
    watch = report.get("watch") or {}
    items = watch.get("items") or []
    if not items:
        return ""
    rows = []
    for i in items:
        dl = i.get("days_left")
        if not i.get("return_date"):
            rd = '<span style="color:#888780;font-size:12px;">未登记</span>'
        elif isinstance(dl, int) and dl >= 0:
            rd = '<span class="%s">%s(还剩 %d 天)</span>' % (
                "soon" if dl <= 7 else "cnt", _esc(i["return_date"]), dl)
        else:
            rd = '<span style="color:#888780;font-size:12px;">%s(已过)</span>' % _esc(i["return_date"])
        rows.append(
            '<tr>'
            '<td>%s</td><td>%s</td><td style="text-align:right;">%s</td>'
            '<td>%s</td><td>%s</td>'
            '<td style="color:#5F5E5A;font-size:12px;">%s</td>'
            '</tr>'
            % (_esc(i["hero"]), _esc(i["skin"]),
               _esc(i["price"] or "-"),
               _verdict_badge(i["verdict"]), rd,
               _esc(i["reason"]))
        )
    return """
<section class="watch">
  <div class="watch-head">关注的皮肤 · %d 款(会持续追踪返场窗口)</div>
  <table>
    <thead><tr><th>英雄</th><th>皮肤</th><th style="text-align:right;">点券</th>
    <th>当前状态</th><th>返场日期</th><th>说明</th></tr></thead>
    <tbody>%s</tbody>
  </table>
</section>""" % (len(items), "".join(rows))


def _hero_blocks(report):
    out = []
    for h in report["heroes"]:
        skins_html = "".join(_skin_row(sk) for sk in h["missing"])
        if not skins_html:
            skins_html = ('<tr><td colspan="5" style="color:#5F5E5A;">'
                          '该英雄的皮肤已集齐,或缺失皮肤数据不可见</td></tr>')
        watch_tag = '<span class="tag hot">关注</span>' if h.get("watched") else ""
        out.append("""
<section class="hero">
  <div class="hero-head">
    <span class="hero-name">%s</span>
    %s
    <span class="tag">%s</span>
    <span class="meta">场次 %s · 战力 %s · 缺失 %d 款(可赠送 %d · 待返场 %d)</span>
  </div>
  <table>
    <thead><tr><th>皮肤</th><th>品质</th><th style="text-align:right;">点券</th><th>状态</th><th>判定依据</th></tr></thead>
    <tbody>%s</tbody>
  </table>
</section>""" % (_esc(h["name"] or "英雄ID %s" % h["heroId"]), watch_tag, _esc(h["sources"]),
                _esc(h["games"] or "-"), _esc(h["power"] or "-"), h["missing_total"],
                len(h["giftable"]), len(h["on_return"]), skins_html))
    return "".join(out)


def _hintbar():
    return """
<div class="hintbar">
  <b>怎么读这排数字:</b>前三个是"情况"(他有多少、这次分析了哪些英雄、缺多少),
  后两个是"结论"——<b style="color:#3B6D11;">现在就能送</b>是今天就能买来送出去的;
  <b>离最近的返场</b>是你目标清单里最近一次返场窗口,快到 7 天以内会变红。
  「要等返场」的那些不用天天盯,登记了返场日期就会自动倒计时。
</div>"""


def _legend(report):
    s = report["summary"]
    extra = ('&nbsp;|&nbsp; 待确认 %d 款' % s["unknown_total"]) if s.get("unknown_total") else ""
    return """
<div class="legend">
  <b>可赠送</b> 商城在售,现在就能送 &nbsp;|&nbsp;
  <b>返场时可送</b> 限定/限时皮肤,要等直售返场窗口 &nbsp;|&nbsp;
  <b>不可赠送</b> 荣耀典藏、战令、抽奖返场、赛季绝版等,永久无法转移%s
</div>""" % extra


def blocks(report):
    """总控台与报告页共用的内容块(不含外层 <html> 与页面样式)。"""
    return ('<div class="blocks">' + "".join([
        _card_block(report),
        _alert_block(report),
        _wishlist_block(report),
        _watch_block(report),
        _hero_blocks(report),
    ]) + '</div>')


# ---------------------------------------------------------------
# 完整单文件报告
# ---------------------------------------------------------------

def _notes_block(report):
    """报告页里的备注区: 写框在最上面, 时间线跟在下面。"""
    s = report["summary"]
    notes = s.get("notes") or []
    items = []
    for n in reversed(notes[-8:]):
        tags = []
        for h in n.get("parsed_heroes") or []:
            tags.append('<span class="tag">英雄 %s</span>' % _esc(h))
        for k in n.get("parsed_skins") or []:
            tags.append('<span class="tag skin">皮肤 %s</span>' % _esc(k))
        items.append(
            '<div class="note">'
            '<div class="note-at">%s</div>'
            '<div class="note-text">%s</div>'
            '<div class="note-tags">%s</div>'
            '</div>' % (_esc(n.get("at", "")), _esc(n.get("text", "")),
                        "".join(tags) or '<span class="note-dim">未识别到英雄</span>')
        )
    timeline = "".join(items) or '<div class="note-dim">还没有备注</div>'
    return """
<section class="notes writebox">
  <div class="notes-head">✍️ 写一条备注 · 就在这个框里输入</div>
  <div class="write-hint">
    想到什么就写什么,英雄名和皮肤名会自动认出来并加进关注列表。
    例:「今天开黑他说其实也挺喜欢公孙离的,可惜当年没买到祈雪灵祝」。
    保存后立刻写进你电脑上的档案。
  </div>
  <textarea id="noteBox" placeholder="这里输入……例:今天开黑他说其实也挺喜欢公孙离的"></textarea>
  <div class="row">
    <button id="noteSave">保存这条备注</button>
    <span class="msg" id="noteMsg"></span>
  </div>
  <div class="notes-head" style="margin-top:18px;">备注时间线</div>
  %s
</section>""" % timeline


_PAGE_CSS = """
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #FAFAF7; color: #2C2C2A; margin: 0; padding: 24px; font-size: 13px; }
  .wrap { max-width: 900px; margin: 0 auto; }
  h1 { font-size: 20px; font-weight: 500; margin: 0 0 4px; }
  .sub { color: #5F5E5A; font-size: 13px; margin-bottom: 16px; }
  .banner { border-radius: 12px; padding: 12px 16px; font-size: 13px; margin-bottom: 16px;
            line-height: 1.85; }
  .banner.warn { background: #FAEEDA; border: 0.5px solid #EF9F27; color: #633806; }
  .banner.info { background: #E6F1FB; border: 0.5px solid #85B7EB; color: #0C447C; }
  .banner a { color: #185FA5; font-weight: 500; }
  .notes { background: #FBFAF4; border: 0.5px solid #97C459; border-radius: 12px;
           padding: 16px; margin-bottom: 16px; }
  .notes-head { font-size: 14.5px; font-weight: 500; margin-bottom: 8px; color: #27500A; }
  .write-hint { font-size: 12px; color: #5F5E5A; line-height: 1.75; margin-bottom: 8px; }
  .note { border-left: 2px solid #D3D1C7; padding: 2px 0 2px 12px; margin-bottom: 10px; }
  .note-at { font-size: 11px; color: #888780; }
  .note-text { font-size: 13px; margin: 2px 0 4px; }
  .note-tags { display: flex; gap: 6px; flex-wrap: wrap; }
  .note-dim { font-size: 11px; color: #888780; }
  .writebox textarea { width: 100%; box-sizing: border-box; font-family: inherit;
       font-size: 13px; border: 0.5px solid #D3D1C7; border-radius: 8px; padding: 8px 10px;
       min-height: 64px; color: #2C2C2A; background: #FFFFFF; resize: vertical; line-height: 1.6; }
  .writebox textarea:focus { outline: none; border-color: #85B7EB; }
  .writebox .row { display: flex; align-items: center; gap: 10px; margin-top: 8px; flex-wrap: wrap; }
  .writebox button { font-family: inherit; font-size: 12.5px; border-radius: 8px; cursor: pointer;
       border: 0.5px solid #97C459; background: #EAF3DE; color: #27500A; padding: 7px 16px; }
  .writebox button:hover { border-color: #6E9B2E; }
  .writebox .msg { font-size: 12px; color: #5F5E5A; }
  .topnav { font-size: 12px; margin-bottom: 10px; }
  .topnav a { color: #185FA5; text-decoration: none; }
  .footer { color: #888780; font-size: 12px; line-height: 1.7; margin-top: 24px; }
"""


def render(report):
    s = report["summary"]
    friend = s["friend"] or {}
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    title_name = s.get("profile_name") or friend.get("name") or "未知"

    onsale_note = ""
    if s.get("onsale_count"):
        onsale_note = " · 在售名单 %d 条" % s["onsale_count"]
    profile_line = ""
    if s.get("profile_role"):
        profile_line = " · %s" % _esc(s["profile_role"])

    parts = [
        '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n',
        '<title>送礼建议 - %s</title>\n<style>%s%s</style>\n</head>\n' % (
            _esc(title_name), _PAGE_CSS, REPORT_CSS),
        '<body data-profile="%s">\n<div class="wrap">\n' % _esc(title_name),
        '<div class="topnav"><a href="http://127.0.0.1:8765/">← 回到总控台(建档 / 改判定 / 换朋友)</a></div>\n',
        '<h1>送礼建议 · %s</h1>\n' % _esc(title_name),
        '<div class="sub">生成时间 %s%s · 英雄范围: 常用 ∪ 战力 Top %d ∪ 你关注的%s</div>\n' % (
            now, profile_line, s["top_n"], onsale_note),
        # 备注框放在本页最上面,避免"说要拉到最下面,结果在中部"
        _notes_block(report),
        '<div class="banner info">这是单独存的一份报告文件。日常用<b>总控台</b>一个页面就够了'
        '(建档、写备注、给皮肤标返场日期都在那):打开 '
        '<a href="http://127.0.0.1:8765/">http://127.0.0.1:8765/</a>,'
        '或终端里运行 <code>python3 -m gifttool serve</code>。</div>\n',
        _card_block(report),
        _hintbar(),
        _legend(report),
        _alert_block(report),
        _wishlist_block(report),
        _watch_block(report),
        _hero_blocks(report),
        '<div class="footer">\n',
        '判定规则顺序: 你的人工标注 → 内置皮肤级标注 → 在售名单 → 永久不可赠送关键词 → 限定/限时关键词 → 直售价格兜底。<br>\n',
        '看到判错的?在总控台页面点一下就能改判,改动写进 data/skin_notes.json,以后一直生效。<br>\n',
        '最终以游戏内皮肤详情页是否显示「赠送」按钮为准; 赠送需满足: 赠送方等级≥15、好友满 3 天(QQ 好友免)、\n',
        '亲密度≥100、同大区同系统(iOS/安卓不能互赠)、每款对同一好友限赠 1 次、每日上限 5 次。<br>\n',
        '数据来自王者营地公开接口,仅供个人学习研究; 请使用小号 CK, 勿用于商业用途。\n</div>\n</div>\n',
        """<script>
(function () {
  // 报告页是静态文件,写备注要调本地服务。file:// 打开也能用(服务端开了 CORS)。
  var API = "http://127.0.0.1:8765";
  var PROFILE = document.body.getAttribute("data-profile") || "";
  var box = document.getElementById("noteBox");
  var msg = document.getElementById("noteMsg");
  var btn = document.getElementById("noteSave");
  if (!box || !btn) return;

  function say(t, good) {
    msg.textContent = t;
    msg.style.color = good ? "#27500A" : "#A32D2D";
  }

  btn.onclick = function () {
    var text = (box.value || "").trim();
    if (!text) { say("先写点什么再保存"); box.focus(); return; }
    if (!PROFILE) { say("这份报告没关联档案"); return; }
    say("正在保存…", true);
    fetch(API + "/api/friend/note", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: PROFILE, text: text })
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (!j.ok) { say("✗ " + (j.error || "保存失败")); return; }
      var parts = [];
      if (j.heroes && j.heroes.length) parts.push("英雄 " + j.heroes.join("、"));
      if (j.skins && j.skins.length) parts.push("皮肤 " + j.skins.join("、"));
      say(parts.length ? "已保存,并识别到:" + parts.join(" / ")
                       : "已保存(这次没认出英雄名)", true);
      box.value = "";
    }).catch(function () {
      say("连不上本地服务。先在终端运行: python3 -m gifttool serve");
    });
  };
})();
</script>
</body>
</html>""",
    ]
    return "".join(parts)
