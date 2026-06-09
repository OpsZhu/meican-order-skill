#!/usr/bin/env python3
"""
美餐自动点餐脚本
自动完成 meican.com 平台的点餐流程
"""

import argparse
import json
import os
import random
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("错误：需要 'requests' 包，请执行：pip install requests")
    sys.exit(1)

try:
    import pytz
except ImportError:
    print("错误：需要 'pytz' 包，请执行：pip install pytz")
    sys.exit(1)

# keyring 可选，用于安全存储凭据
try:
    import keyring
    _HAS_KEYRING = True
except ImportError:
    _HAS_KEYRING = False


# --- 常量 ---
BASE_URL = "https://meican.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
CONFIG_PATH = Path.home() / ".meican-order.json"
PREFS_PATH = Path.home() / ".meican-preferences.json"
KEYRING_SERVICE = "meican-order"

# OAuth 客户端凭证（美餐 Web 前端公开凭证，所有用户相同）
DEFAULT_CLIENT_ID = "Xqr8w0Uk4ciodqfPwjhav5rdxTaYepD"
DEFAULT_CLIENT_SECRET = "vD11O6xI9bG3kqYRu9OyPAHkRGxLh4E"

# API 端点
URL_LOGIN = f"{BASE_URL}/account/directlogin"
URL_CALENDAR = f"{BASE_URL}/preorder/api/v2.1/calendarItems/list"
URL_RESTAURANTS = f"{BASE_URL}/preorder/api/v2.1/restaurants/list"
URL_DISHES = f"{BASE_URL}/preorder/api/v2.1/restaurants/show"
URL_ORDER = f"{BASE_URL}/preorder/api/v2.1/orders/add"
URL_ORDER_CANCEL = "https://www.meican.com/forward/api/v2.1/orders/delete"
URL_FORWARD_ADDRESS = "https://www.meican.com/forward/api/v2.1/corpaddresses/getmulticorpaddress"
URL_CLOSET_SHOW = "https://www.meican.com/forward/api/v2.1/orders/closetShow"
URL_OPEN_CLOSET_BOX = "https://www.meican.com/forward/api/v2.1/orders/openClosetBox"

# 让餐时间窗口（只能在规定时间段内让餐）
SHARE_TIME_WINDOWS = {
    "breakfast": (8.5, 10.5),   # 8:30-10:30
    "lunch": (11.5, 13.5),      # 11:30-13:30
    "dinner": (17.5, 19.5),     # 17:30-19:30
}


# --- 偏好管理（内联） ---

DEFAULT_PREFS = {
    "order_history": [],
    "favorite_restaurants": [],
    "disliked_restaurants": [],
    "favorite_types": [],
    "disliked_types": [],
    "favorite_dishes": [],
    "disliked_dishes": [],
}


def load_preferences():
    """加载偏好数据，不存在则创建默认文件"""
    if not PREFS_PATH.exists():
        save_preferences(DEFAULT_PREFS)
        return DEFAULT_PREFS.copy()
    with open(PREFS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    for key, val in DEFAULT_PREFS.items():
        if key not in data:
            data[key] = val
    return data


def save_preferences(prefs):
    """保存偏好数据到文件"""
    with open(PREFS_PATH, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)


def record_order(dish_name, restaurant_name, target_date="", meal_type="", dish_type=""):
    """记录一次成功的点餐"""
    prefs = load_preferences()
    entry = {
        "dish": dish_name,
        "restaurant": restaurant_name,
        "type": dish_type,
        "target_date": target_date,
        "meal_type": meal_type,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    prefs["order_history"].append(entry)
    if len(prefs["order_history"]) > 200:
        prefs["order_history"] = prefs["order_history"][-200:]
    save_preferences(prefs)
    return entry


def remove_order_from_history(target_date, meal_type):
    """取消订单时按日期+餐类从历史记录中删除对应条目"""
    prefs = load_preferences()
    history = prefs["order_history"]
    if not history:
        return []
    removed = []
    new_history = []
    for h in history:
        if h.get("target_date") == target_date and h.get("meal_type") == meal_type:
            removed.append(h["dish"])
        else:
            new_history.append(h)
    if removed:
        prefs["order_history"] = new_history
        save_preferences(prefs)
    return removed


def get_history_stats():
    """分析点餐历史，返回频率统计"""
    prefs = load_preferences()
    history = prefs["order_history"]
    if not history:
        return {"dishes": {}, "restaurants": {}, "types": {}}

    dish_counter = Counter(h["dish"] for h in history)
    rest_counter = Counter(h["restaurant"] for h in history if h.get("restaurant"))
    type_counter = Counter(h["type"] for h in history if h.get("type"))

    return {
        "dishes": dict(dish_counter.most_common(20)),
        "restaurants": dict(rest_counter.most_common(10)),
        "types": dict(type_counter.most_common(10)),
        "total_orders": len(history),
    }


def score_dish(dish_name, restaurant_name, prefs=None, stats=None):
    """为菜品计算偏好得分"""
    if prefs is None:
        prefs = load_preferences()
    if stats is None:
        stats = get_history_stats()

    score = 0

    if any(d in dish_name for d in prefs.get("disliked_dishes", [])):
        return -100
    if any(r == restaurant_name for r in prefs.get("disliked_restaurants", [])):
        return -50
    if any(t in dish_name for t in prefs.get("disliked_types", [])):
        return -30

    if any(d in dish_name for d in prefs.get("favorite_dishes", [])):
        score += 30
    if any(r == restaurant_name for r in prefs.get("favorite_restaurants", [])):
        score += 20
    if any(t in dish_name for t in prefs.get("favorite_types", [])):
        score += 15

    dish_freq = stats.get("dishes", {})
    rest_freq = stats.get("restaurants", {})

    if dish_name in dish_freq:
        score += min(dish_freq[dish_name], 10)
    if restaurant_name in rest_freq:
        score += min(rest_freq[restaurant_name], 5)

    return score


def filter_by_preference(dishes, min_score=0):
    """基于偏好评分筛选菜品"""
    prefs = load_preferences()
    stats = get_history_stats()

    scored = []
    for dish in dishes:
        dish_name = dish.get("name", "")
        restaurant = dish.get("_restaurant", "")
        s = score_dish(dish_name, restaurant, prefs, stats)
        if s >= min_score:
            scored.append((s, dish))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored]


# --- 凭据管理 ---

def _get_credential(username):
    """
    按优先级获取密码：
    1. 系统密钥环（keyring）- 最安全
    2. 环境变量 MEICAN_PASSWORD
    3. 配置文件（不推荐，仅作兼容）
    """
    # 优先从密钥环获取
    if _HAS_KEYRING:
        stored_pw = keyring.get_password(KEYRING_SERVICE, username)
        if stored_pw:
            return stored_pw

    # 其次从环境变量获取
    env_pw = os.environ.get("MEICAN_PASSWORD")
    if env_pw:
        return env_pw

    return None


def _store_credential(username, password):
    """将凭据安全存储到系统密钥环"""
    if _HAS_KEYRING:
        keyring.set_password(KEYRING_SERVICE, username, password)
        return True
    return False


def load_config():
    """
    加载配置。凭据获取优先级：
    1. 系统密钥环（需安装 keyring 包）
    2. 环境变量 MEICAN_USERNAME / MEICAN_PASSWORD
    3. 配置文件（仅用于非敏感配置，密码存于此时会提示迁移）
    """
    config = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)

    # 用户名：环境变量 > 配置文件
    config["username"] = os.environ.get("MEICAN_USERNAME", config.get("username", ""))

    if not config["username"]:
        print("错误：未找到美餐账号。")
        print("请通过以下任一方式提供：")
        if _HAS_KEYRING:
            print("  方式1（推荐）：运行本脚本 --setup 进行安全配置")
        print("  方式2：设置环境变量 MEICAN_USERNAME / MEICAN_PASSWORD")
        print(f"  方式3：在 {CONFIG_PATH} 中配置 username")
        sys.exit(1)

    # 密码：密钥环 > 环境变量 > 配置文件
    password = _get_credential(config["username"])

    if not password:
        # 最后尝试从配置文件读取（不推荐）
        password = config.get("password", "")
        if password:
            print(f"[安全警告] 密码以明文存储在 {CONFIG_PATH}")
            if _HAS_KEYRING:
                print("           正在迁移到系统密钥环...")
                if _store_credential(config["username"], password):
                    # 迁移成功后从配置文件中移除密码
                    config.pop("password", None)
                    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                        json.dump(config, f, ensure_ascii=False, indent=2)
                    print("           [OK] 已迁移至密钥环，配置文件中的密码已移除")
            else:
                print("           建议安装 keyring 包：pip install keyring")
                print("           然后运行 --setup 完成安全迁移")

    if not password:
        print("错误：未找到美餐密码。")
        print("请通过以下任一方式提供：")
        if _HAS_KEYRING:
            print("  方式1（推荐）：运行本脚本 --setup 进行安全配置")
        print("  方式2：设置环境变量 MEICAN_PASSWORD")
        sys.exit(1)

    config["password"] = password
    config["client_id"] = os.environ.get("MEICAN_CLIENT_ID", config.get("client_id", ""))
    config["client_secret"] = os.environ.get("MEICAN_CLIENT_SECRET", config.get("client_secret", ""))

    return config


def setup_credentials():
    """交互式安全配置凭据（存储到系统密钥环）"""
    if not _HAS_KEYRING:
        print("错误：安全存储需要 keyring 包，请先安装：pip install keyring")
        sys.exit(1)

    import getpass
    print("=== 美餐点餐 - 安全凭据配置 ===")
    print("密码将存储在操作系统密钥环中（Windows 凭据管理器 / macOS 钥匙串 / Linux Secret Service）\n")

    username = input("美餐账号（邮箱）：").strip()
    if not username:
        print("错误：账号不能为空")
        sys.exit(1)

    password = getpass.getpass("美餐密码（输入不可见）：")
    if not password:
        print("错误：密码不能为空")
        sys.exit(1)

    _store_credential(username, password)
    print(f"\n[OK] 凭据已安全存储到系统密钥环")

    # 确保配置文件中有 username 但没有 password
    config = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)

    config["username"] = username
    config.pop("password", None)  # 移除明文密码

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"[OK] 用户名已写入 {CONFIG_PATH}（密码不存储在文件中）")


# --- API 客户端 ---
class MeiCanClient:
    """美餐 API 客户端"""

    def __init__(self, username, password, client_id="", client_secret=""):
        self.client_id = client_id or DEFAULT_CLIENT_ID
        self.client_secret = client_secret or DEFAULT_CLIENT_SECRET
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._login(username, password)

    def _login(self, username, password):
        """登录美餐（带 OAuth 凭证以支持 forward 接口）"""
        login_url = f"{URL_LOGIN}?client_id={self.client_id}&client_secret={self.client_secret}"
        resp = self.session.post(login_url, data={
            "username": username,
            "password": password,
            "loginType": "username",
            "remember": True
        })
        if resp.status_code != 200 or "用户名或密码错误" in resp.text:
            raise RuntimeError(f"登录失败：{resp.text[:200]}")
        # 提取 OAuth bearer token
        self._bearer_token = ""
        for c in self.session.cookies:
            if c.name == "sat":
                self._bearer_token = c.value
                break
        print(f"[OK] 已登录：{username}")

    def _get(self, url, params=None):
        """发送 GET 请求"""
        if params is None:
            params = {}
        params["noHttpGetCache"] = int(time.time() * 1000)
        from urllib.parse import urlencode
        full_url = f"{url}?{urlencode(sorted(params.items()))}"
        resp = self.session.get(full_url)
        resp.raise_for_status()
        if not resp.text.strip():
            return {}
        try:
            return resp.json()
        except Exception:
            print(f"[警告] API 返回非 JSON 响应（长度={len(resp.text)}），可能需要重新登录")
            return {}

    def get_tabs(self):
        """获取可用的点餐时间段"""
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        data = self._get(URL_CALENDAR, {
            "beginDate": today,
            "endDate": end_date,
            "withOrderDetail": False
        })
        tabs = []
        tz = pytz.timezone("Asia/Shanghai")
        for date_item in data.get("dateList", []):
            for item in date_item.get("calendarItemList", []):
                target_time_ms = item.get("targetTime", 0)
                target_time_dt = datetime.fromtimestamp(
                    int(target_time_ms) / 1000, tz=tz
                )
                item["_tab_uid"] = item.get("userTab", {}).get("uniqueId", "")
                item["_target_time"] = target_time_dt
                item["_target_date"] = target_time_dt.strftime("%Y-%m-%d")
                item["_addresses"] = [
                    a for a in item.get("userTab", {}).get("corp", {}).get("addressList", [])
                ]
                tabs.append(item)
        return tabs

    def get_available_tabs(self):
        """获取状态为 AVAILABLE 的时间段"""
        tabs = self.get_tabs()
        return [t for t in tabs if t.get("status") == "AVAILABLE"]

    def get_restaurants(self, tab):
        """获取指定时间段的餐厅列表"""
        data = self._get(URL_RESTAURANTS, {
            "tabUniqueId": tab["_tab_uid"],
            "targetTime": tab["_target_time"]
        })
        return data.get("restaurantList", [])

    def get_dishes(self, restaurant_uid, tab):
        """获取指定餐厅的菜品列表"""
        data = self._get(URL_DISHES, {
            "restaurantUniqueId": restaurant_uid,
            "tabUniqueId": tab["_tab_uid"],
            "targetTime": tab["_target_time"]
        })
        return data.get("dishList", [])

    def list_all_dishes(self, tab):
        """获取某时间段下所有餐厅的全部菜品"""
        restaurants = self.get_restaurants(tab)
        all_dishes = []
        for rest in restaurants:
            dishes = self.get_dishes(rest["uniqueId"], tab)
            for dish in dishes:
                dish["_restaurant"] = rest.get("name", "未知")
            all_dishes.extend(dishes)
        return all_dishes

    def place_order(self, dish, tab, address_uid="", address_keyword=""):
        """下单"""
        order_data = json.dumps([{"count": "1", "dishId": "{}".format(dish["id"])}])
        corp_address_uid = ""
        user_address_uid = ""
        if address_uid:
            corp_address_uid = address_uid
            user_address_uid = address_uid
        elif tab.get("_addresses"):
            addr = tab["_addresses"][0]
            corp_address_uid = addr.get("uniqueId", "")
            user_address_uid = addr.get("uniqueId", "")

        if not corp_address_uid:
            target_hour = None
            if tab.get("_target_time") and hasattr(tab["_target_time"], "hour"):
                target_hour = tab["_target_time"].hour
            fallback_uid = self.get_address_uid(
                keyword=address_keyword, target_hour=target_hour
            )
            corp_address_uid = fallback_uid
            user_address_uid = fallback_uid

        from urllib.parse import urlencode
        params = {
            "order": order_data,
            "tabUniqueId": tab["_tab_uid"],
            "targetTime": tab["_target_time"],
            "corpAddressUniqueId": corp_address_uid,
            "userAddressUniqueId": user_address_uid,
        }
        full_url = f"{URL_ORDER}?{urlencode(sorted(params.items()))}"
        resp = self.session.post(full_url)
        resp.raise_for_status()
        result = resp.json()
        if result.get("status") and result["status"] != "SUCCESSFUL":
            raise RuntimeError(result.get("message", result.get("status")))
        return result

    def get_address_uid(self, keyword="", target_hour=None):
        """获取取餐地址 UID
        
        优先从已有订单的 corpOrderUser 提取，若找不到则 fallback 到 forward API。
        """
        # 方法1：从已有订单中提取
        begin = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        data = self._get(URL_CALENDAR, {
            "beginDate": begin,
            "endDate": end_date,
            "withOrderDetail": True
        })
        tz = pytz.timezone("Asia/Shanghai")
        candidates = []
        for date_item in data.get("dateList", []):
            for item in date_item.get("calendarItemList", []):
                corp_user = item.get("corpOrderUser")
                if corp_user:
                    addr = corp_user.get("corpAddress", {})
                    if addr and addr.get("uniqueId"):
                        addr_str = addr.get("address", "") + addr.get("pickUpLocation", "")
                        if not keyword or keyword in addr_str:
                            item_time_ms = item.get("targetTime", 0)
                            item_hour = datetime.fromtimestamp(
                                int(item_time_ms) / 1000, tz=tz
                            ).hour
                            candidates.append((item_hour, addr.get("uniqueId")))
        if target_hour is not None and candidates:
            for hour, uid in candidates:
                if hour == target_hour:
                    return uid
        if candidates:
            return candidates[0][1]

        # 方法2：fallback 到 forward API 获取企业地址列表
        forward_uid = self._get_address_from_forward_api(keyword)
        if forward_uid:
            return forward_uid

        return ""

    def _get_address_from_forward_api(self, keyword=""):
        """通过 forward API 获取企业地址 UID
        
        当 addressList 为空且没有已有订单时，使用 forward API 的
        corpaddresses/getmulticorpaddress 接口获取可用地址。
        认证方式：使用登录后 session 中的 sat cookie 作为 Bearer token。
        """
        sat = self.session.cookies.get("sat", domain=".meican.com")
        if not sat:
            return ""

        namespace = ""
        # 从 tabs 中获取 corp namespace
        tabs = self.get_tabs()
        for tab in tabs:
            corp = tab.get("userTab", {}).get("corp", {})
            ns = corp.get("namespace", "")
            if ns:
                namespace = ns
                break

        if not namespace:
            return ""

        url = f"{URL_FORWARD_ADDRESS}?client_id={self.client_id}&client_secret={self.client_secret}&namespace={namespace}"
        headers = {"Authorization": f"Bearer {sat}"}
        try:
            resp = requests.get(url, headers=headers)
            if resp.status_code != 200:
                return ""
            result = resp.json()
            if result.get("resultCode") != "OK":
                return ""
            addr_data = result.get("data", {})
            addr_list = addr_data.get("addressList", [])
            recent_list = addr_data.get("recentList", [])

            # 优先从 recentList 中匹配（最近使用的地址）
            if keyword:
                for recent in recent_list:
                    addr_str = recent.get("address", "") + recent.get("pickUpLocation", "")
                    if keyword in addr_str:
                        return recent.get("uniqueId", "")

            # 然后从 addressList 中匹配
            if keyword:
                for addr_item in addr_list:
                    name = addr_item.get("name", "")
                    final = addr_item.get("finalValue", {})
                    addr_str = name + final.get("pickUpLocation", "")
                    if keyword in addr_str:
                        return final.get("uniqueId", "")

            # 无 keyword 时：优先返回最近使用的地址
            if recent_list:
                return recent_list[0].get("uniqueId", "")
            # 其次返回 addressList 第一个
            if addr_list:
                return addr_list[0].get("finalValue", {}).get("uniqueId", "")

            return ""
        except Exception:
            return ""

    def get_ordered_tabs(self):
        """获取已下单的时间段"""
        today = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        data = self._get(URL_CALENDAR, {
            "beginDate": today,
            "endDate": end_date,
            "withOrderDetail": True
        })
        ordered = []
        tz = pytz.timezone("Asia/Shanghai")
        for date_item in data.get("dateList", []):
            for item in date_item.get("calendarItemList", []):
                if item.get("status") in ("ORDERED", "ORDER"):
                    target_time_ms = item.get("targetTime", 0)
                    target_time_dt = datetime.fromtimestamp(
                        int(target_time_ms) / 1000, tz=tz
                    )
                    item["_tab_uid"] = item.get("userTab", {}).get("uniqueId", "")
                    item["_target_time"] = target_time_dt
                    item["_target_date"] = target_time_dt.strftime("%Y-%m-%d")
                    ordered.append(item)
        return ordered

    def get_order_from_tab(self, tab):
        """从已下单的时间段中提取订单信息"""
        order_info = tab.get("corpOrderUser", {})
        if not order_info:
            return None
        order_id = order_info.get("uniqueId", "")
        restaurant_items = order_info.get("restaurantItemList", [])
        dishes = []
        for rest_item in restaurant_items:
            rest_uid = rest_item.get("uniqueId", "")
            dish_items = rest_item.get("dishItemList", [])
            for dish_item in dish_items:
                dish_obj = dish_item.get("dish", {})
                dish_name = dish_obj.get("name", "未知")
                dish_id = dish_obj.get("id", "")
                dishes.append({
                    "dish_name": dish_name,
                    "dish_id": dish_id,
                    "restaurant": rest_uid,
                    "count": dish_item.get("count", 1),
                })
        return {
            "order_id": order_id,
            "tab_uid": tab.get("_tab_uid", ""),
            "target_time": tab.get("_target_time", ""),
            "title": tab.get("title", ""),
            "dishes": dishes,
        }

    def cancel_order(self, order_uid):
        """取消订单（使用 forward 接口 + OAuth 认证）"""
        cancel_url = (
            f"{URL_ORDER_CANCEL}?client_id={self.client_id}&client_secret={self.client_secret}"
        )
        headers = {
            "Authorization": f"bearer {self._bearer_token}",
            "Clientid": self.client_id,
            "Clientsecret": self.client_secret,
        }
        resp = self.session.post(cancel_url, data={
            "uniqueId": order_uid,
            "type": "CORP_ORDER",
            "restoreCart": "false",
        }, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def closet_show(self, order_unique_id):
        """获取订单柜门信息（使用 forward 接口 + OAuth 认证）"""
        url = (
            f"{URL_CLOSET_SHOW}?client_id={self.client_id}"
            f"&client_secret={self.client_secret}"
            f"&uniqueId={order_unique_id}"
        )
        headers = {
            "Authorization": f"bearer {self._bearer_token}",
            "Clientid": self.client_id,
            "Clientsecret": self.client_secret,
        }
        resp = self.session.get(url, headers=headers)
        resp.raise_for_status()
        result = resp.json()
        if result.get("resultCode") != "OK":
            raise RuntimeError(
                f"获取柜门信息失败：{result.get('resultDescription', '未知错误')}"
            )
        return result.get("data", {})

    def open_closet_box(self, order_id, closet_id, box_number_list):
        """打开智能餐柜柜门（使用 forward 接口 + OAuth 认证）"""
        url = (
            f"{URL_OPEN_CLOSET_BOX}?client_id={self.client_id}"
            f"&client_secret={self.client_secret}"
        )
        headers = {
            "Authorization": f"bearer {self._bearer_token}",
            "Clientid": self.client_id,
            "Clientsecret": self.client_secret,
        }
        resp = self.session.post(url, data={
            "orderId": str(order_id),
            "closetId": str(closet_id),
            "boxNumberList": str(box_number_list),
        }, headers=headers)
        resp.raise_for_status()
        result = resp.json()
        if result.get("resultCode") != "OK":
            raise RuntimeError(
                f"开柜门失败：{result.get('resultDescription', '未知错误')}"
            )
        return result


# --- 筛选 ---
def filter_dishes(dishes, expect_keywords="", exclude_keywords=""):
    """按包含/排除关键字筛选菜品"""
    result = set(range(len(dishes)))

    if expect_keywords.strip():
        keywords = [k.strip() for k in expect_keywords.split("|") if k.strip()]
        matched = set()
        for kw in keywords:
            for i, dish in enumerate(dishes):
                if kw in dish.get("name", ""):
                    matched.add(i)
        result = result & matched if matched else set()

    if exclude_keywords.strip():
        keywords = [k.strip() for k in exclude_keywords.split("|") if k.strip()]
        excluded = set()
        for kw in keywords:
            for i, dish in enumerate(dishes):
                if kw in dish.get("name", ""):
                    excluded.add(i)
        result = result - excluded

    return [dishes[i] for i in sorted(result)]


def find_tab_by_keyword(tabs, keyword):
    """按关键字匹配时间段"""
    if not keyword:
        return tabs[0] if tabs else None
    for tab in tabs:
        if keyword in str(tab):
            return tab
    return tabs[0] if tabs else None


def find_address_by_keyword(tab, keyword):
    """按关键字匹配取餐地址"""
    if not keyword:
        return ""
    addresses = tab.get("_addresses", [])
    for addr in addresses:
        addr_str = addr.get("address", "") + addr.get("pickUpLocation", "")
        if keyword in addr_str:
            return addr.get("uniqueId", "")
    return ""


# --- 主程序 ---
MEAL_CN = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}
MEAL_ORDER = ("breakfast", "lunch", "dinner")


def classify_meal(tab):
    """根据时间段判断餐类"""
    h = tab["_target_time"].hour
    if h < 10:
        return "breakfast"
    if h < 14:
        return "lunch"
    return "dinner"


def classify_meal_for_share(hour):
    """根据当前时间判断可让餐的餐类"""
    for mt, (start, end) in SHARE_TIME_WINDOWS.items():
        if start <= hour < end:
            return mt
    return None


def share_meal(client, tab_keyword=None):
    """让餐：将已点的餐品让给他人取餐

    流程：
    1. 校验时间窗口
    2. 获取当天对应餐类的订单
    3. 调用 closetShow 获取柜门信息
    4. 调用 openClosetBox 打开柜门
    5. 输出让餐详情供 agent 推送飞书通知
    """
    now = datetime.now()
    current_hour = now.hour + now.minute / 60.0

    # 确定餐类
    meal_type = None
    if tab_keyword:
        for mt, cn in MEAL_CN.items():
            if cn in tab_keyword or mt in tab_keyword.lower():
                meal_type = mt
                break
        if not meal_type:
            if "早" in tab_keyword:
                meal_type = "breakfast"
            elif "午" in tab_keyword:
                meal_type = "lunch"
            elif "晚" in tab_keyword:
                meal_type = "dinner"
    else:
        meal_type = classify_meal_for_share(current_hour)

    if not meal_type:
        if tab_keyword:
            print(f"[失败] 无法识别餐类 \"{tab_keyword}\"，请使用：早餐/午餐/晚餐")
        else:
            print("[拒绝] 当前时间不在任何让餐时间窗口内")
            print("       让餐时间：早餐 8:00-10:00 | 午餐 11:00-13:00 | 晚餐 17:00-19:00")
        return None

    # 时间窗口校验
    window = SHARE_TIME_WINDOWS.get(meal_type)
    if window and not (window[0] <= current_hour < window[1]):
        start_h, start_m = int(window[0]), int((window[0] % 1) * 60)
        end_h, end_m = int(window[1]), int((window[1] % 1) * 60)
        print(f"[拒绝] 当前时间不在 {MEAL_CN[meal_type]} 让餐时间窗口内")
        print(f"       {MEAL_CN[meal_type]}让餐时间：{start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d}")
        print(f"       当前时间：{now.hour:02d}:{now.minute:02d}")
        return None

    # 获取今天的订单
    today = now.strftime("%Y-%m-%d")
    ordered_tabs = client.get_ordered_tabs()
    today_orders = [t for t in ordered_tabs if t.get("_target_date") == today]

    target_tab = None
    for ot in today_orders:
        mt = classify_meal(ot)
        if mt == meal_type:
            target_tab = ot
            break

    if not target_tab:
        print(f"[失败] 今天没有 {MEAL_CN[meal_type]} 的订单")
        return None

    # 提取订单 uniqueId
    order_info = target_tab.get("corpOrderUser", {})
    order_unique_id = order_info.get("uniqueId", "")

    if not order_unique_id:
        print("[失败] 无法获取订单 ID")
        return None

    # 获取柜门信息
    print(f"[让餐] 正在获取 {MEAL_CN[meal_type]} 柜门信息...")
    try:
        closet_data = client.closet_show(order_unique_id)
    except Exception as e:
        print(f"[失败] 获取柜门信息失败：{e}")
        return None

    # 检查是否已取餐
    has_unreceived = False
    for box_item in closet_data.get("orderDishInBoxList", []):
        for dish_item in box_item.get("orderClosetDishList", []):
            if not dish_item.get("userReceived", False):
                has_unreceived = True
    if not has_unreceived:
        print("[失败] 餐品已被取走，无法让餐")
        return None

    # 检查柜门是否关闭
    if closet_data.get("isShut", False):
        print("[失败] 智能餐柜已关闭，无法打开柜门")
        return None

    # 检查柜门可用时间
    available_start = closet_data.get("closetAvailableStartTime", "")
    available_end = closet_data.get("closetAvailableEndTime", "")
    if available_start and available_end:
        current_time_str = now.strftime("%H:%M")
        if current_time_str < available_start or current_time_str > available_end:
            print(f"[拒绝] 当前时间不在柜门可用时间范围内")
            print(f"       柜门可用时间：{available_start}-{available_end}")
            print(f"       当前时间：{current_time_str}")
            return None

    # 提取柜门数据
    dish_boxes = closet_data.get("orderDishInBoxList", [])
    if not dish_boxes:
        print("[失败] 订单无柜门信息（可能不是智能餐柜配送）")
        return None

    # 收集让餐详情和开柜参数
    share_info = {
        "meal_type": meal_type,
        "meal_cn": MEAL_CN[meal_type],
        "title": closet_data.get("title", ""),
        "pickup_location": closet_data.get("pickUpLocation", ""),
        "real_name": closet_data.get("realName", ""),
        "dishes": [],
        "opened_boxes": [],
    }

    open_results = []

    for box_item in dish_boxes:
        closet = box_item.get("closet", {})
        closet_id = closet.get("closetId", "")
        closet_code = closet.get("closetCode", "")

        for dish_item in box_item.get("orderClosetDishList", []):
            if dish_item.get("userReceived", False):
                continue  # 已取餐的跳过

            box_number = dish_item.get("boxNumber", "")
            dish_name = dish_item.get("name", "")
            restaurant_name = dish_item.get("restaurantName", "")
            price_in_cent = dish_item.get("priceInCent", 0)

            share_info["dishes"].append({
                "dish_name": dish_name,
                "restaurant": restaurant_name,
                "price": price_in_cent / 100,
                "closet_code": closet_code,
                "box_number": box_number,
            })

            # 使用 closetShow 返回的 orderUniqueId 作为 openClosetBox 的 orderId
            order_id = closet_data.get("orderUniqueId", closet_data.get("uniqueId", ""))

            # 打开柜门
            print(f"[让餐] 打开柜门 {closet_code}/{box_number}...")
            try:
                client.open_closet_box(order_id, closet_id, box_number)
                print(f"[OK] 柜门已打开：{closet_code} 号柜 {box_number} 号门")
                share_info["opened_boxes"].append({
                    "closet_code": closet_code,
                    "box_number": box_number,
                    "closet_id": closet_id,
                })
                open_results.append(True)
            except Exception as e:
                print(f"[失败] 打开柜门 {closet_code}/{box_number} 失败：{e}")
                open_results.append(False)

    if not open_results or not any(open_results):
        print("[失败] 所有柜门打开失败，让餐未完成")
        return None

    # 输出让餐结果
    print()
    print("=" * 40)
    print(f"[让餐成功] {MEAL_CN[meal_type]}")
    print("=" * 40)

    for d in share_info["dishes"]:
        print(f"  菜品：{d['dish_name']}")
        print(f"  餐厅：{d['restaurant']}")
        if d['price'] > 0:
            print(f"  价格：{d['price']}元")

    print(f"  取餐地点：{share_info['pickup_location']}")

    for box in share_info["opened_boxes"]:
        print(f"  柜号：{box['closet_code']} | 柜门：{box['box_number']}")

    print()
    print("[提示] 柜门已打开，请通知同事前往取餐")

    # 输出结构化 JSON 供 agent 解析
    print()
    print("---SHARE_JSON---")
    print(json.dumps(share_info, ensure_ascii=False))
    print("---END_SHARE_JSON---")

    return share_info


def report_existing_order(client, ordered_tab, meal_type):
    """打印单个已下订单，带 [已有订单] 标签与菜品名称"""
    order = client.get_order_from_tab(ordered_tab)
    if not order:
        print(f"  [已有订单][{MEAL_CN[meal_type]}] {ordered_tab.get('title', '')}（无法获取详情）")
        return
    dishes_str = ", ".join(
        f"{d['dish_name']}({d['restaurant']})" for d in order["dishes"]
    )
    # 添加时间信息用于调试
    target_time = ordered_tab.get("_target_time")
    if target_time:
        time_str = f"{target_time.hour}:{target_time.minute:02d}"
        print(f"  [已有订单][{MEAL_CN[meal_type]}] {dishes_str} (时间:{time_str})")
    else:
        print(f"  [已有订单][{MEAL_CN[meal_type]}] {dishes_str}")


def wait_for_restaurant(client, tab, restaurant_keyword, max_retries, interval_seconds):
    """等待指定餐厅出现，返回 True 表示餐厅已出现，False 表示超时失败

    每次等待间隔为随机值（interval_seconds 到 interval_seconds*2 之间）
    以避免多人同时重试导致服务端压力过大
    """
    if not restaurant_keyword:
        return True

    print(f"[等待] 等待餐厅 \"{restaurant_keyword}\" 出现...")
    print(f"[等待] 最大重试 {max_retries} 次，基准间隔 {interval_seconds} 秒")

    elapsed_time = 0
    for retry in range(1, max_retries + 1):
        restaurants = client.get_restaurants(tab)
        matched = [
            r for r in restaurants
            if restaurant_keyword.lower() in r.get("name", "").lower()
        ]

        if matched:
            matched_names = ", ".join(r["name"] for r in matched)
            print(f"[等待] 第 {retry} 次检查：餐厅已出现 - {matched_names}")
            return True

        # 生成随机等待时间（interval 到 interval*2 之间）
        # 例如 interval=300 → 等待 300-600 秒之间
        random_interval = random.randint(interval_seconds, interval_seconds * 2)
        elapsed_time += random_interval
        remaining_estimate = (max_retries - retry) * interval_seconds * 1.5

        print(f"[等待] 第 {retry} 次检查：餐厅未出现")
        print(f"[等待] 本次等待 {random_interval} 秒（随机范围 {interval_seconds}-{interval_seconds*2}）后重试...")
        print(f"[等待] 已等待约 {elapsed_time} 秒，剩余最多约 {int(remaining_estimate)} 秒")

        if retry < max_retries:
            time.sleep(random_interval)

    total_estimate = max_retries * interval_seconds * 1.5
    print(f"[失败] 等待超时：餐厅 \"{restaurant_keyword}\" 未出现")
    print(f"[失败] 预估总等待时间：约 {int(total_estimate)} 秒，重试次数：{max_retries}")
    return False


def _order_week(client, config, expect_keywords, exclude_keywords,
                address_keyword, use_prefs, list_only,
                wait_restaurant=None, wait_retry=10, wait_interval=300):
    """整周点餐：智能计算目标日期并点餐

    逻辑：
    - 周日/周六执行 → 点下周周一到周五
    - 周一到周五执行 → 点今天到周五（本周剩余天数）
    """
    from datetime import datetime

    today = datetime.now()
    weekday = today.weekday()  # 周一=0, 周二=1, ..., 周日=6

    # 计算目标日期列表
    week_dates = []
    weekday_names = []

    if weekday >= 5:  # 周六(5)或周日(6)
        # 点下周周一到周五
        days_until_monday = 7 - weekday if weekday == 6 else 2  # 周日→+1, 周六→+2
        for i in range(5):
            date = today + timedelta(days=days_until_monday + i)
            week_dates.append(date.strftime("%Y-%m-%d"))
            weekday_names.append(["周一", "周二", "周三", "周四", "周五"][i])
        mode_desc = "下周"
    else:
        # 点本周剩余天数（今天到周五）
        days_to_order = 5 - weekday  # 周一→5天, 周二→4天, ..., 周五→1天
        for i in range(days_to_order):
            date = today + timedelta(days=i)
            week_dates.append(date.strftime("%Y-%m-%d"))
            # 根据实际日期确定星期名称
            date_weekday = date.weekday()  # 周一=0, ..., 周五=4
            weekday_names.append(["周一", "周二", "周三", "周四", "周五"][date_weekday])
        mode_desc = "本周剩余"

    print(f"\n[整周模式] {mode_desc}天数：{len(week_dates)} 天")
    print(f"[整周模式] 点餐日期：")
    for i, (date, wname) in enumerate(zip(week_dates, weekday_names), 1):
        print(f"  {i}. {date}（{wname}）")

    if list_only:
        print("\n[提示] --list 模式下仅显示日期，不执行点餐")
        return

    # 统计结果
    total_success = 0
    total_attempted = 0
    results_by_date = {}

    for i, (target_date, weekday_name) in enumerate(zip(week_dates, weekday_names), 1):
        print(f"\n{'='*50}")
        print(f"[{weekday_name}] {target_date}")
        print(f"{'='*50}")

        # 检查该日期已下订单
        ordered_by_meal = {}
        all_ordered = client.get_ordered_tabs()

        # 过滤该日期的订单并按时段分类
        date_orders = [ot for ot in all_ordered if ot.get("_target_date") == target_date]
        for ot in date_orders:
            mt = classify_meal(ot)
            # 每个时段只记录一个订单（避免重复）
            if mt not in ordered_by_meal:
                ordered_by_meal[mt] = ot

        # 获取该日期可用时段
        available_tabs = client.get_available_tabs()
        date_tabs = [t for t in available_tabs if t.get("_target_date") == target_date]

        if not date_tabs and not ordered_by_meal:
            print(f"[信息] {weekday_name} 无可用时段，跳过")
            results_by_date[target_date] = {"status": "无时段", "meals": {}}
            continue

        # 显示已下订单
        if ordered_by_meal:
            print(f"\n--- {weekday_name} 已下订单 ---")
            for mt in MEAL_ORDER:
                if mt in ordered_by_meal:
                    report_existing_order(client, ordered_by_meal[mt], mt)

        # 构建待点餐清单
        pending = {}
        for t in date_tabs:
            mt = classify_meal(t)
            if mt not in ordered_by_meal and mt not in pending:
                pending[mt] = t

        if not pending:
            print(f"\n[完成] {weekday_name} 三餐均已下单，无需重复点餐")
            results_by_date[target_date] = {"status": "全部已下单", "meals": ordered_by_meal}
            continue

        pending_names = ", ".join(MEAL_CN[m] for m in MEAL_ORDER if m in pending)
        print(f"\n[信息] {weekday_name} 待点餐时段：{pending_names}")

        # 对每个时段下单
        day_success = 0
        day_attempted = len(pending)
        meals_result = {}

        for mt in MEAL_ORDER:
            if mt not in pending:
                continue

            tab = pending[mt]
            print(f"\n--- {MEAL_CN[mt]} ---")

            success = _order_one_tab(
                client, tab, config, expect_keywords, exclude_keywords,
                address_keyword, use_prefs, False, target_date,
                wait_restaurant, wait_retry, wait_interval
            )

            meals_result[mt] = success
            if success:
                day_success += 1

        total_success += day_success
        total_attempted += day_attempted
        results_by_date[target_date] = {
            "status": f"下单 {day_success}/{day_attempted}",
            "meals": meals_result
        }

    # 输出汇总报告
    print(f"\n{'='*50}")
    print(f"[整周完成] {mode_desc}点餐汇总报告")
    print(f"{'='*50}")

    for i, (target_date, weekday_name) in enumerate(zip(week_dates, weekday_names), 1):
        result = results_by_date.get(target_date, {})
        status = result.get("status", "未处理")
        print(f"  {weekday_name} {target_date}: {status}")

    print(f"\n总计：成功下单 {total_success}/{total_attempted} 餐")
    if total_attempted == 0:
        print(f"[信息] {mode_desc}所有时段均已下单，无需重复点餐")
    elif total_success == total_attempted:
        print(f"[成功] {mode_desc}所有待点餐时段均已成功下单！")
    else:
        print(f"[部分成功] {total_attempted - total_success} 个时段下单失败，请检查日志")


def _order_one_tab(client, tab, config, expect_keywords, exclude_keywords,
                   address_keyword, use_prefs, list_only, target_date,
                   wait_restaurant=None, wait_retry=10, wait_interval=600):
    """对单个时间段执行筛选和下单流程，返回 True 表示已下单成功"""
    print(f"[信息] 选中时间段：{tab.get('title', '未知')}（{tab['_target_date']}）")

    # 等待指定餐厅出现
    if wait_restaurant:
        if not wait_for_restaurant(client, tab, wait_restaurant, wait_retry, wait_interval):
            return False

    all_dishes = client.list_all_dishes(tab)
    if not all_dishes:
        print("[信息] 当前没有可用菜品")
        return False
    print(f"[信息] 共 {len(all_dishes)} 道菜品")

    meals_config = config.get("meals", {})
    meal_type = classify_meal(tab)
    meal_conf = meals_config.get(meal_type, {})

    # 等待餐厅优先筛选（如果指定了 --wait-restaurant）
    if wait_restaurant:
        restaurant_filtered = [
            d for d in all_dishes
            if wait_restaurant.lower() in d.get("_restaurant", "").lower()
        ]
        if restaurant_filtered:
            print(f"[信息] 等待餐厅 \"{wait_restaurant}\" 有 {len(restaurant_filtered)} 道菜品")
            all_dishes = restaurant_filtered
        else:
            print(f"[警告] 等待餐厅 \"{wait_restaurant}\" 无可用菜品，使用全部餐厅")

    # 分时段餐厅筛选
    meal_restaurants = meal_conf.get("restaurants", [])
    if not use_prefs:
        meal_restaurants = []
    if meal_restaurants:
        restaurant_filtered = [
            d for d in all_dishes
            if any(r in d.get("_restaurant", "") for r in meal_restaurants)
        ]
        if restaurant_filtered:
            print(f"[信息] 餐厅偏好筛选后剩余 {len(restaurant_filtered)} 道")
            all_dishes = restaurant_filtered
        else:
            print("[警告] 偏好餐厅无可用菜品，使用全部餐厅")

    # 合并排除关键词
    meal_exclude = meal_conf.get("exclude", [])
    if not use_prefs:
        meal_exclude = []
    combined_exclude = exclude_keywords
    if meal_exclude:
        extra = "|".join(meal_exclude)
        combined_exclude = f"{exclude_keywords}|{extra}" if exclude_keywords else extra

    # 关键字筛选
    filtered = filter_dishes(all_dishes, expect_keywords, combined_exclude)
    print(f"[信息] 关键字筛选后剩余 {len(filtered)} 道")

    # 预算筛选
    budget_config = config.get("budget", {})
    if budget_config:
        max_price = budget_config.get(meal_type, 0)
        if max_price > 0:
            max_cent = int(max_price * 100)
            budget_filtered = [d for d in filtered if d.get("priceInCent", 0) <= max_cent]
            if budget_filtered:
                print(f"[信息] 预算筛选({max_price}元内)后剩余 {len(budget_filtered)} 道")
                filtered = budget_filtered
            else:
                print(f"[警告] 无菜品在{max_price}元预算内，跳过预算限制")

    # 偏好筛选
    if use_prefs and filtered:
        preferred = filter_by_preference(filtered, min_score=-1)
        if preferred:
            print(f"[信息] 偏好筛选后剩余 {len(preferred)} 道")
            filtered = preferred
        else:
            print("[信息] 偏好筛选过严，仅使用关键字结果")

    if not filtered:
        print("[警告] 没有菜品符合条件，请尝试放宽筛选")
        return False

    # 列表模式
    if list_only:
        prefs_data = load_preferences() if use_prefs else None
        stats = get_history_stats() if use_prefs else None
        print("\n--- 可选菜品 ---")
        for i, dish in enumerate(filtered, 1):
            restaurant = dish.get("_restaurant", "未知")
            price = dish.get("priceInCent", 0) / 100
            indicator = ""
            if use_prefs and prefs_data:
                s = score_dish(dish["name"], restaurant, prefs_data, stats)
                if s >= 20:
                    indicator = " ***"
                elif s >= 10:
                    indicator = " **"
                elif s > 0:
                    indicator = " *"
            print("  {:3d}. [{}] {} - {}元{}".format(i, restaurant, dish['name'], int(price), indicator))
        print(f"\n共计：{len(filtered)} 道菜品")
        if use_prefs:
            print("  (* = 符合偏好, ** = 较符合, *** = 非常喜欢)")
        return False

    # 下单重试机制（最多3次）
    max_retries = 3
    available_dishes = filtered.copy()  # 可用菜品池

    for retry in range(1, max_retries + 1):
        if not available_dishes:
            print("[警告] 没有菜品可供选择")
            return False

        chosen = random.choice(available_dishes)
        print(f"[下单] 选中：{chosen['name']}（{chosen.get('_restaurant', '')}）")

        address_uid = find_address_by_keyword(tab, address_keyword)

        try:
            client.place_order(chosen, tab, address_uid, address_keyword=address_keyword)
            print("[OK] 下单成功！")
            print(f"     菜品：{chosen['name']}")
            if chosen.get("_restaurant"):
                print(f"     餐厅：{chosen['_restaurant']}")
            record_order(
                chosen["name"], chosen.get("_restaurant", ""),
                target_date=target_date or tab.get("_target_date", ""),
                meal_type=meal_type,
            )
            print("[信息] 已记录到点餐历史")
            return True
        except Exception as e:
            error_msg = str(e)
            print(f"[失败] 下单失败：{error_msg}")

            # 判断是否可以重试（售罄、过期、已有订单等）
            can_retry = any(keyword in error_msg for keyword in
                ["售罄", "过期", "已过期", "已有订单", "不可用", "已关闭"])

            if can_retry and retry < max_retries:
                # 从可用菜品池中移除失败的菜品
                available_dishes = [d for d in available_dishes if d["id"] != chosen["id"]]
                print(f"[重试] 第 {retry} 次失败，从剩余 {len(available_dishes)} 道菜品中重新选择...")
            else:
                print(f"[失败] 第 {retry} 次失败，不再重试")
                return False

    return False


def main():
    parser = argparse.ArgumentParser(description="美餐自动点餐")
    parser.add_argument("--list", action="store_true", help="列出可用菜品（不下单）")
    parser.add_argument("--tab", type=str, default=None, help="时间段关键字筛选")
    parser.add_argument("--date", type=str, default=None, help="指定日期（YYYY-MM-DD 或 +N 表示N天后）")
    parser.add_argument("--expect", type=str, default=None, help="包含关键字（多个用 | 分隔）")
    parser.add_argument("--exclude", type=str, default=None, help="排除关键字（多个用 | 分隔）")
    parser.add_argument("--address", type=str, default=None, help="取餐地址关键字")
    parser.add_argument("--no-prefs", action="store_true", help="禁用偏好筛选")
    parser.add_argument("--cancel", action="store_true", help="取消当前订单")
    parser.add_argument("--orders", action="store_true", help="查看已下的订单")
    parser.add_argument("--reorder", action="store_true", help="取消当前订单并重新点餐")
    parser.add_argument("--share", action="store_true", help="让餐：将已点的餐品让给他人取餐")
    parser.add_argument("--setup", action="store_true", help="安全配置凭据（存储到系统密钥环）")
    # 等待餐厅参数
    parser.add_argument("--wait-restaurant", type=str, default=None,
                        help="等待指定餐厅出现（模糊匹配餐厅名称）")
    parser.add_argument("--wait-retry", type=int, default=10,
                        help="等待餐厅最大重试次数（默认10）")
    parser.add_argument("--wait-interval", type=int, default=300,
                        help="每次等待间隔秒数（默认300，实际等待随机300-600）")
    parser.add_argument("--week", action="store_true",
                        help="点下周整周（周一到周五）所有餐")
    args = parser.parse_args()

    # 安全配置模式
    if args.setup:
        setup_credentials()
        sys.exit(0)

    # 加载配置
    config = load_config()
    username = config["username"]
    password = config["password"]
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")

    # 命令行参数覆盖配置
    tab_keyword = args.tab if args.tab is not None else config.get("tab_keyword", "")
    expect_keywords = args.expect if args.expect is not None else config.get("expect_keywords", "")
    exclude_keywords = args.exclude if args.exclude is not None else config.get("exclude_keywords", "")
    address_keyword = args.address if args.address is not None else config.get("address_keyword", "")
    use_prefs = not args.no_prefs

    # 解析日期参数
    target_date = None
    if args.date:
        if args.date.startswith("+"):
            days = int(args.date[1:])
            target_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        else:
            target_date = args.date

    # 初始化客户端
    try:
        client = MeiCanClient(username, password, client_id, client_secret)
    except RuntimeError as e:
        print(f"[失败] {e}")
        sys.exit(1)

    # --- 整周点餐模式 ---
    if args.week:
        _order_week(client, config, expect_keywords, exclude_keywords,
                    address_keyword, use_prefs, args.list,
                    args.wait_restaurant, args.wait_retry, args.wait_interval)
        sys.exit(0)

    # --- 让餐 ---
    if args.share:
        share_meal(client, tab_keyword)
        sys.exit(0)

    # --- 查看已下订单 ---
    if args.orders:
        ordered_tabs = client.get_ordered_tabs()
        if target_date:
            ordered_tabs = [t for t in ordered_tabs if t.get("_target_date") == target_date]
        if not ordered_tabs:
            print("[信息] 当前没有已下的订单")
            sys.exit(0)
        print(f"\n--- 已下订单（共 {len(ordered_tabs)} 个）---")
        for i, otab in enumerate(ordered_tabs, 1):
            order = client.get_order_from_tab(otab)
            if order:
                dishes_str = ", ".join(
                    f"{d['dish_name']}({d['restaurant']})" for d in order["dishes"]
                )
                print(f"  {i}. [已有订单][{order['title']}] {dishes_str}")
            else:
                print(f"  {i}. [已有订单][{otab.get('title', '未知')}]（无法获取详情）")
        sys.exit(0)

    # --- 取消订单 ---
    if args.cancel or args.reorder:
        ordered_tabs = client.get_ordered_tabs()
        if target_date:
            ordered_tabs = [t for t in ordered_tabs if t.get("_target_date") == target_date]
        target_tabs = ordered_tabs
        if tab_keyword:
            target_tabs = [t for t in ordered_tabs if tab_keyword in str(t)]

        if not target_tabs:
            print("[信息] 没有找到可取消的订单")
            if not args.reorder:
                sys.exit(0)
        else:
            tab_to_cancel = target_tabs[0]
            order = client.get_order_from_tab(tab_to_cancel)
            order_uid = tab_to_cancel.get("corpOrderUser", {}).get("uniqueId", "")

            if order:
                dishes_str = ", ".join(d["dish_name"] for d in order["dishes"])
                print(f"[取消] 正在取消订单：{dishes_str}")
            else:
                print(f"[取消] 正在取消订单：{tab_to_cancel.get('title', '')}")

            if not order_uid:
                print("[失败] 无法获取订单 ID")
                sys.exit(1)

            try:
                client.cancel_order(order_uid)
                print("[OK] 订单已取消")
                cancel_date = tab_to_cancel.get("_target_date", "")
                cancel_meal = classify_meal(tab_to_cancel) if tab_to_cancel.get("_target_time") else ""
                removed = remove_order_from_history(cancel_date, cancel_meal)
                if removed:
                    print(f"[信息] 已从点餐历史中移除：{', '.join(removed)}")
            except Exception as e:
                print(f"[失败] 取消订单失败：{e}")
                sys.exit(1)

        if not args.reorder:
            sys.exit(0)

        print("\n[信息] 开始重新点餐...")

    # --- 预检查：目标日期已下订单（直接查线上，不依赖本地历史）---
    ordered_by_meal = {}
    if target_date:
        all_ordered = client.get_ordered_tabs()
        for ot in all_ordered:
            if ot.get("_target_date") == target_date:
                mt = classify_meal(ot)
                ordered_by_meal.setdefault(mt, ot)

    # --- 获取可用时段 ---
    available_tabs = client.get_available_tabs()
    if target_date:
        available_tabs = [t for t in available_tabs if t.get("_target_date") == target_date]

    if not available_tabs and not ordered_by_meal:
        print("[信息] 当前没有可用的点餐时间段")
        if target_date:
            print(f"       指定日期：{target_date}")
        sys.exit(0)

    if target_date:
        print(f"[信息] 目标日期 {target_date}：可用时段 {len(available_tabs)} 个，已下单时段 {len(ordered_by_meal)} 个")
    else:
        print(f"[信息] 找到 {len(available_tabs)} 个可用时间段")

    # 显示已下订单详情
    if ordered_by_meal:
        print("\n--- 目标日期已下订单 ---")
        for mt in MEAL_ORDER:
            if mt in ordered_by_meal:
                report_existing_order(client, ordered_by_meal[mt], mt)

    # --- 多餐模式：指定日期且未指定时段且非 reorder ---
    multi_mode = bool(target_date) and not tab_keyword and not args.reorder

    if multi_mode:

        # 构建待点餐清单（按时段去重）
        pending = {}
        for t in available_tabs:
            mt = classify_meal(t)
            if mt not in ordered_by_meal and mt not in pending:
                pending[mt] = t

        if not pending:
            print("\n[完成] 目标日期三餐均已下单，无需重复点餐")
            sys.exit(0)

        pending_names = ", ".join(MEAL_CN[m] for m in MEAL_ORDER if m in pending)
        print(f"\n[信息] 待点餐时段：{pending_names}")

        success_count = 0
        for mt in MEAL_ORDER:
            if mt not in pending:
                continue
            tab = pending[mt]
            print(f"\n=== 处理 {MEAL_CN[mt]} ===")
            if _order_one_tab(client, tab, config, expect_keywords, exclude_keywords,
                              address_keyword, use_prefs, args.list, target_date,
                              args.wait_restaurant, args.wait_retry, args.wait_interval):
                success_count += 1

        if args.list:
            sys.exit(0)
        print(f"\n[完成] 本次自动下单 {success_count}/{len(pending)} 餐")
        sys.exit(0)

    # --- 单时段模式 ---
    if not available_tabs:
        print("[信息] 当前没有可用的点餐时间段")
        sys.exit(0)

    tab = None
    if target_date and not tab_keyword:
        for t in available_tabs:
            if classify_meal(t) == "lunch":
                tab = t
                break
    if not tab:
        tab = find_tab_by_keyword(available_tabs, tab_keyword)
    if not tab:
        print("[失败] 未找到匹配的时间段")
        sys.exit(1)

    # 若该时段已下单，直接返回（reorder 场景除外，reorder 已在前面取消）
    selected_meal = classify_meal(tab)
    if not args.reorder and selected_meal in ordered_by_meal:
        print(f"\n[信息] {MEAL_CN[selected_meal]} 已下单，无需重复点餐")
        report_existing_order(client, ordered_by_meal[selected_meal], selected_meal)
        sys.exit(0)

    _order_one_tab(client, tab, config, expect_keywords, exclude_keywords,
                   address_keyword, use_prefs, args.list, target_date,
                   args.wait_restaurant, args.wait_retry, args.wait_interval)


if __name__ == "__main__":
    main()
