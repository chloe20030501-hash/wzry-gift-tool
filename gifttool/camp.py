"""王者营地非公开 API 客户端(接口路径来自开源项目逆向,仅供学习研究)。

三组核心接口:
  allrolelistv3      营地ID -> 角色ID + 区服信息
  h5getheroskinlist  全量皮肤目录 + 目标玩家已拥有皮肤 + 各英雄战力
  profile/herolist   目标玩家常用英雄(场次)
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

MAIN_URL = "https://kohcamp.qq.com"
GAME_URL = "https://ssl.kohsocialapp.qq.com:10001"

EP_ALL_ROLES = GAME_URL + "/game/allrolelistv3"
EP_SKIN_LIST = GAME_URL + "/play/h5getheroskinlist"
EP_PROFILE = MAIN_URL + "/userprofile/profile"
EP_PROFILE_INDEX = MAIN_URL + "/game/koh/profile"
EP_PROFILE_HERO_LIST = MAIN_URL + "/game/profile/herolist"


class CampError(Exception):
    """营地接口调用失败(returnCode 非 0 或网络错误)。"""


def parse_ck(ck):
    """解析 CK,格式为 userId&&token(抓包获得,务必使用小号)。"""
    ck = ck.strip()
    if "&&" in ck:
        userid, token = ck.split("&&", 1)
        userid, token = userid.strip(), token.strip()
        if userid and token:
            return userid, token
    raise CampError("CK 格式应为 userId&&token,请检查抓包结果")


def base_headers():
    """伪装成王者营地 App 的客户端头(与抓包看到的一致)。"""
    return {
        "Host": "kohcamp.qq.com",
        "origin": "https://kohcamp.qq.com",
        "istrpcrequest": "true",
        "cchannelid": "2002",
        "cclientversioncode": "2047933506",
        "cclientversionname": "9.103.0723",
        "ccurrentgameid": "20001",
        "cgameid": "20001",
        "cgzip": "1",
        "cisarm64": "true",
        "crand": str(int(time.time())),
        "csupportarm64": "true",
        "csystem": "android",
        "csystemversioncode": "35",
        "csystemversionname": "15",
        "cpuhardware": "qcom",
        "gameareaid": "0",
        "gameid": "20001",
        "gameserverid": "0",
        "gameroleid": "0",
        "gameusersex": "1",
        "openid": uuid.uuid4().hex.upper(),
        "tinkerid": "2047933506_64_0",
        "content-encrypt": "",
        "accept-encrypt": "",
        "noencrypt": "1",
        "x-client-proto": "https",
        "content-type": "application/json; charset=UTF-8",
        "user-agent": "okhttp/4.9.1",
        "kohdimgender": "1",
    }


class CampClient:
    def __init__(self, ck=None, userid=None, token=None, timeout=30):
        if ck:
            userid, token = parse_ck(ck)
        if not userid or not token:
            raise CampError("缺少 CK(userid/token)")
        self.userid = userid
        self.token = token
        self.timeout = timeout

    # ---------- 基础请求 ----------

    def _request(self, url, payload=None, form=None, auth=True, raw=False):
        headers = base_headers()
        if auth:
            headers["token"] = self.token
            headers["userid"] = self.userid
        if form is not None:
            headers["content-type"] = "application/x-www-form-urlencoded"
            headers["Host"] = "ssl.kohsocialapp.qq.com:10001"
            body = urllib.parse.urlencode(form).encode()
        elif payload is not None:
            body = json.dumps(payload).encode()
        else:
            body = None
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                text = resp.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            raise CampError("HTTP %s: %s" % (e.code, url))
        except urllib.error.URLError as e:
            raise CampError("网络错误: %s (%s)" % (e.reason, url))
        try:
            data = json.loads(text)
        except ValueError:
            raise CampError("响应不是 JSON(可能被加密或需要新的客户端版本): %s" % text[:200])
        if raw:
            return data
        code = data.get("returnCode", data.get("retcode", 0))
        if code not in (0, "0"):
            raise CampError("接口返回错误 returnCode=%s,请确认 CK 有效/未过期" % code)
        return data.get("data", data)

    # ---------- 业务接口 ----------

    def resolve_roles(self, friend_user_id):
        """营地ID -> 角色列表(roleId、区服)。返回原始 data,结构由调用方防御性解析。"""
        form = {
            "friendUserId": str(friend_user_id),
            "token": self.token,
            "userId": self.userid,
        }
        return self._request(EP_ALL_ROLES, form=form, raw=True)

    def get_skin_info(self, friend_user_id):
        """全量皮肤目录 + 已拥有皮肤 + 英雄战力(核心接口,一个顶三个)。"""
        form = {
            "noCache": "0",
            "recommendPrivacy": "0",
            "friendUserId": str(friend_user_id),
            "cChannelId": "2002",
            "cClientVersionCode": "2047933506",
            "cClientVersionName": "9.103.0723",
            "cCurrentGameId": "20001",
            "cGameId": "20001",
            "cGzip": "1",
            "cIsArm64": "true",
            "cRand": str(int(time.time() * 1000)),
            "cSupportArm64": "true",
            "cSystem": "android",
            "cSystemVersionCode": "35",
            "cSystemVersionName": "15",
            "cpuHardware": "qcom",
            "gameAreaId": "0",
            "gameId": "20001",
            "gameRoleId": "0",
            "gameServerId": "0",
            "gameUserSex": "1",
            "openId": uuid.uuid4().hex.upper(),
            "tinkerId": "2047933506_64_0",
            "token": self.token,
            "userId": self.userid,
        }
        return self._request(EP_SKIN_LIST, form=form, raw=True)

    def get_profile_hero_list(self, friend_user_id, role_id):
        """目标玩家常用英雄(带场次/胜率,字段名随版本可能变化,调用方防御性解析)。"""
        payload = {
            "targetUserId": str(friend_user_id),
            "recommendPrivacy": 0,
            "targetRoleId": str(role_id),
        }
        return self._request(EP_PROFILE_HERO_LIST, payload=payload, raw=True)

    def get_profile_index(self, friend_user_id, role_id):
        payload = {
            "targetUserId": str(friend_user_id),
            "recommendPrivacy": 0,
            "targetRoleId": str(role_id),
            "apiVersion": 2,
            "resVersion": 3,
        }
        return self._request(EP_PROFILE_INDEX, payload=payload, raw=True)
