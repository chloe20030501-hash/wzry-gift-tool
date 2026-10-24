"""内置示例数据(结构仿真 h5getheroskinlist / profile-herolist 响应)。

用于 --demo 模式跑通全流程; 接入真实 CK 后这些数据会被接口响应替换。
皮肤品质与获取方式按公开资料核对(官网「皮肤探究课」、百度百科英雄条目)。
"""

DEMO_FRIEND = {"name": "示例好友·小妲己", "roleId": "3731578254", "server": "微信128区"}

# 全量皮肤目录(heroSkinConfList): skinId -> detail
DEMO_SKIN_CONF = {
    # 貂蝉(141)
    "14101": {"iHeroId": 141, "szTitle": "异域舞娘", "szHeroTitle": "貂蝉", "szClass": "A",
              "iPrice": 288, "skin_worth": 288, "accessWay": "商城直售", "classTypeName": ["勇者"]},
    "14102": {"iHeroId": 141, "szTitle": "圣诞恋歌", "szHeroTitle": "貂蝉", "szClass": "S+",
              "iPrice": 788, "skin_worth": 788, "accessWay": "商城直售", "classTypeName": ["史诗"]},
    "14103": {"iHeroId": 141, "szTitle": "仲夏夜之梦", "szHeroTitle": "貂蝉", "szClass": "S++",
              "iPrice": 1688, "skin_worth": 1688, "accessWay": "商城直售", "classTypeName": ["传说"]},
    "14104": {"iHeroId": 141, "szTitle": "猫影幻舞", "szHeroTitle": "貂蝉", "szClass": "S++",
              "iPrice": 1688, "skin_worth": 1688, "accessWay": "FMVP限定·限时售卖",
              "classTypeName": ["传说", "FMVP", "限定"]},
    "14105": {"iHeroId": 141, "szTitle": "遇见胡旋", "szHeroTitle": "貂蝉", "szClass": "S++",
              "iPrice": 1788, "skin_worth": 1788, "accessWay": "敦煌研究院联动·限时售卖",
              "classTypeName": ["传说", "敦煌", "限定"]},
    "14106": {"iHeroId": 141, "szTitle": "唤灵魅影", "szHeroTitle": "貂蝉", "szClass": "S+",
              "iPrice": 888, "skin_worth": 888, "accessWay": "五五朋友节·限时售卖",
              "classTypeName": ["史诗", "五五", "限定"]},
    "14107": {"iHeroId": 141, "szTitle": "幻阙歌", "szHeroTitle": "貂蝉", "szClass": "SR",
              "iPrice": 0, "skin_worth": 20000, "accessWay": "积分夺宝·荣耀水晶兑换",
              "classTypeName": ["荣耀典藏"]},
    "14108": {"iHeroId": 141, "szTitle": "曦玄引", "szHeroTitle": "貂蝉", "szClass": "S++",
              "iPrice": 1788, "skin_worth": 1788, "accessWay": "情人节限定·限时售卖",
              "classTypeName": ["传说", "情人节", "限定"]},
    # 瑶(505)
    "50501": {"iHeroId": 505, "szTitle": "森", "szHeroTitle": "瑶", "szClass": "A",
              "iPrice": 288, "skin_worth": 288, "accessWay": "商城直售", "classTypeName": ["勇者"]},
    "50502": {"iHeroId": 505, "szTitle": "遇见神鹿", "szHeroTitle": "瑶", "szClass": "S+",
              "iPrice": 888, "skin_worth": 888, "accessWay": "敦煌研究院联动·限时售卖",
              "classTypeName": ["史诗", "敦煌", "联动"]},
    "50503": {"iHeroId": 505, "szTitle": "时之祈愿", "szHeroTitle": "瑶", "szClass": "S++",
              "iPrice": 1788, "skin_worth": 1788, "accessWay": "春节限定·限时售卖",
              "classTypeName": ["传说", "春节", "限定"]},
    # 孙悟空(167)
    "16701": {"iHeroId": 167, "szTitle": "地狱火", "szHeroTitle": "孙悟空", "szClass": "S++",
              "iPrice": 1688, "skin_worth": 1688, "accessWay": "商城直售", "classTypeName": ["传说"]},
    "16702": {"iHeroId": 167, "szTitle": "至尊宝", "szHeroTitle": "孙悟空", "szClass": "S+",
              "iPrice": 888, "skin_worth": 888, "accessWay": "大话西游联动·限时售卖",
              "classTypeName": ["史诗", "联动", "限定"]},
    "16703": {"iHeroId": 167, "szTitle": "孙行者", "szHeroTitle": "孙悟空", "szClass": "S+",
              "iPrice": 888, "skin_worth": 888, "accessWay": "西游记联动·限时售卖",
              "classTypeName": ["史诗", "联动", "限定"]},
    "16704": {"iHeroId": 167, "szTitle": "全息碎影", "szHeroTitle": "孙悟空", "szClass": "SR",
              "iPrice": 0, "skin_worth": 20000, "accessWay": "积分夺宝·荣耀水晶兑换",
              "classTypeName": ["荣耀典藏"]},
    # 李白(131)
    "13101": {"iHeroId": 131, "szTitle": "千年之狐", "szHeroTitle": "李白", "szClass": "S+",
              "iPrice": 788, "skin_worth": 788, "accessWay": "商城直售", "classTypeName": ["史诗"]},
    "13102": {"iHeroId": 131, "szTitle": "凤求凰", "szHeroTitle": "李白", "szClass": "S++",
              "iPrice": 1788, "skin_worth": 1788, "accessWay": "鸡年限定·限时售卖",
              "classTypeName": ["传说", "鸡年", "限定"]},
    "13103": {"iHeroId": 131, "szTitle": "鸣剑·曳剑", "szHeroTitle": "李白", "szClass": "S+",
              "iPrice": 0, "skin_worth": 0, "accessWay": "战令限定",
              "classTypeName": ["史诗", "战令"]},
    # 小乔(106,仅战力维度命中)
    "10601": {"iHeroId": 106, "szTitle": "天鹅之梦", "szHeroTitle": "小乔", "szClass": "SR",
              "iPrice": 0, "skin_worth": 20000, "accessWay": "积分夺宝·荣耀水晶兑换",
              "classTypeName": ["荣耀典藏"]},
    "10602": {"iHeroId": 106, "szTitle": "纯白花嫁", "szHeroTitle": "小乔", "szClass": "S+",
              "iPrice": 788, "skin_worth": 788, "accessWay": "情人节限定·限时售卖",
              "classTypeName": ["史诗", "情人节", "限定"]},
    "10603": {"iHeroId": 106, "szTitle": "缤纷独角兽", "szHeroTitle": "小乔", "szClass": "S+",
              "iPrice": 888, "skin_worth": 888, "accessWay": "商城直售", "classTypeName": ["史诗"]},
    "10604": {"iHeroId": 106, "szTitle": "万圣前夜", "szHeroTitle": "小乔", "szClass": "A",
              "iPrice": 288, "skin_worth": 288, "accessWay": "商城直售", "classTypeName": ["勇者"]},
    # 公孙离(199,备注里提到的「关注英雄」,演示建档+备注解析链路)
    "19901": {"iHeroId": 199, "szTitle": "幻舞玲珑", "szHeroTitle": "公孙离", "szClass": "A",
              "iPrice": 288, "skin_worth": 288, "accessWay": "商城直售", "classTypeName": ["勇者"]},
    "19902": {"iHeroId": 199, "szTitle": "花间舞", "szHeroTitle": "公孙离", "szClass": "S+",
              "iPrice": 888, "skin_worth": 888, "accessWay": "商城直售", "classTypeName": ["史诗"]},
    "19903": {"iHeroId": 199, "szTitle": "蜜橘之夏", "szHeroTitle": "公孙离", "szClass": "S+",
              "iPrice": 888, "skin_worth": 888, "accessWay": "夏日限定·限时售卖",
              "classTypeName": ["史诗", "限定"]},
    "19904": {"iHeroId": 199, "szTitle": "无限星赏官", "szHeroTitle": "公孙离", "szClass": "S++",
              "iPrice": 1688, "skin_worth": 1688, "accessWay": "无限王者团联动·限时售卖",
              "classTypeName": ["传说", "联动", "限定"]},
    "19905": {"iHeroId": 199, "szTitle": "祈雪灵祝", "szHeroTitle": "公孙离", "szClass": "S++",
              "iPrice": 1788, "skin_worth": 1788, "accessWay": "虎年限定·限时售卖",
              "classTypeName": ["传说", "虎年", "限定"]},
    "19906": {"iHeroId": 199, "szTitle": "玉兔公主", "szHeroTitle": "公孙离", "szClass": "S+",
              "iPrice": 888, "skin_worth": 888, "accessWay": "兔年限定·限时售卖",
              "classTypeName": ["史诗", "兔年", "限定"]},
}

# 已拥有皮肤(heroSkinList 里的 skinId 列表,附带 iBuy 标记)
DEMO_OWNED_IDS = ["14102", "14103", "16701", "13101", "10604"]

# 各英雄战力(heroList)
DEMO_HERO_POWER = {"141": 12480, "505": 9600, "167": 8100, "131": 6600, "106": 15200, "199": 11800}

# 演示用「当前商城在售/正在直售返场」名单。
# 真实使用时这份名单在 data/onsale.json,用 `onsale add` 维护。
DEMO_ONSALE = {"公孙离·蜜橘之夏"}

# 游戏皮肤总数(全服口径,跟具体账号无关)。
# 口径说明: 只统计正式服已上架、有独立建模的完整皮肤; 星元/星传说不算,
# 返场旧皮肤不重复计数。2026-06 约 801 款, 2026-08 约 820 款, 此处按 2026-10 估 830。
# 真实模式下这个数字直接来自营地接口的 skinCountInfo.totalSkinNum,不用手填。
SKIN_TOTAL = 830
SKIN_TOTAL_ASOF = "2026-10"

DEMO_SKIN_INFO = {
    "heroList": {k: {"heroId": int(k), "heroFightPower": v} for k, v in DEMO_HERO_POWER.items()},
    "skinCountInfo": {"owned": str(len(DEMO_OWNED_IDS)), "totalSkinNum": SKIN_TOTAL,
                      "totalValue": "约 1.2 万点券", "notForSell": 12},
    "heroConfList": {
        "141": {"name": "貂蝉"}, "505": {"name": "瑶"}, "167": {"name": "孙悟空"},
        "131": {"name": "李白"}, "106": {"name": "小乔"}, "199": {"name": "公孙离"},
    },
    "heroSkinList": [{"skinId": sid, "iBuy": 1, "szTitle": DEMO_SKIN_CONF[sid]["szTitle"],
                      "szHeroTitle": DEMO_SKIN_CONF[sid]["szHeroTitle"]} for sid in DEMO_OWNED_IDS],
    "heroSkinConfList": DEMO_SKIN_CONF,
}

# profile/herolist 响应(常用英雄,字段名为演示近似值)
DEMO_PROFILE_HERO = {
    "data": {
        "heroList": [
            {"heroId": 141, "heroName": "貂蝉", "battleCount": 326, "winRate": 54.2},
            {"heroId": 505, "heroName": "瑶", "battleCount": 214, "winRate": 51.8},
            {"heroId": 167, "heroName": "孙悟空", "battleCount": 188, "winRate": 49.6},
            {"heroId": 131, "heroName": "李白", "battleCount": 97, "winRate": 47.3},
        ]
    }
}

# 演示档案: 模拟"建档 + 记了两条备注 + 追踪三款皮肤"的状态
DEMO_PROFILE = {
    "name": "示例好友·小妲己",
    "camp_id": "880123456",
    "role": "微信区 · 安卓",
    "created_at": "2026-10-14 21:30",
    "updated_at": "2026-10-14 21:40",
    "notes": [
        {
            "at": "2026-10-14 21:30",
            "text": "开黑时他说本命是公孙离，最近一直在练，还说打野位也想练个铠",
            "parsed_heroes": ["公孙离", "铠"],
            "parsed_skins": [],
        },
        {
            "at": "2026-10-14 21:40",
            "text": "他说当年没买到公孙离的祈雪灵祝，一直挺遗憾的",
            "parsed_heroes": ["公孙离"],
            "parsed_skins": ["公孙离·祈雪灵祝"],
        },
    ],
    "watch_heroes": [
        {"heroId": 199, "name": "公孙离", "source": "备注: 他自称本命英雄", "added_at": "2026-10-14 21:30"},
        {"heroId": 193, "name": "铠", "source": "备注: 聊天里提到喜欢", "added_at": "2026-10-14 21:30"},
    ],
    "watch_skins": [
        {"key": "公孙离·祈雪灵祝", "heroId": 199, "hero": "公孙离", "skin": "祈雪灵祝",
         "source": "备注: 明确说过想要", "added_at": "2026-10-14 21:40"},
        {"key": "公孙离·蜜橘之夏", "heroId": 199, "hero": "公孙离", "skin": "蜜橘之夏",
         "source": "手动添加", "added_at": "2026-10-14 21:40",
         "return_date": "2026-10-22", "announced": True},
        {"key": "貂蝉·仲夏夜之梦", "heroId": 141, "hero": "貂蝉", "skin": "仲夏夜之梦",
         "source": "手动添加", "added_at": "2026-10-14 21:40"},
    ],
    # 上一次运行的快照(演示"追踪对比出提醒"的效果)
    "runs": [
        {
            "at": "2026-10-14 21:40",
            "giftable": 2, "on_return": 9, "not_giftable": 6,
            "snapshot": {
                "公孙离·祈雪灵祝": {"verdict": "待确认", "owned": False, "found": True,
                                     "hero": "公孙离", "price": 1788},
                "公孙离·蜜橘之夏": {"verdict": "返场时可送", "owned": False, "found": True,
                                     "hero": "公孙离", "price": 888},
                "貂蝉·仲夏夜之梦": {"verdict": "可赠送", "owned": False, "found": True,
                                     "hero": "貂蝉", "price": 1688},
                "__hero_missing__": {
                    "199": ["公孙离·幻舞玲珑", "公孙离·花间舞", "公孙离·无限星赏官",
                            "公孙离·祈雪灵祝", "公孙离·玉兔公主"],
                },
            },
        }
    ],
}


def demo_report(top_n=10, profile=None, onsale=None):
    from . import pipeline
    prof = DEMO_PROFILE if profile is None else profile
    if onsale is None:
        onsale = set(DEMO_ONSALE) | pipeline.load_onsale()
    rep = pipeline.build_report(DEMO_FRIEND, DEMO_SKIN_INFO, DEMO_PROFILE_HERO,
                                top_n=top_n, onsale=onsale, profile=prof)
    if prof is DEMO_PROFILE:
        rep["summary"]["profile_name"] = DEMO_PROFILE["name"]
        rep["summary"]["profile_role"] = DEMO_PROFILE["role"]
    return rep
