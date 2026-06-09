#!/usr/bin/env python3
"""
美餐点餐偏好管理器
负责点餐历史记录、手动偏好标记、智能推荐评分
"""

import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

PREFS_PATH = Path.home() / ".meican-preferences.json"

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
    # 确保所有键存在（向前兼容）
    for key, val in DEFAULT_PREFS.items():
        if key not in data:
            data[key] = val
    return data


def save_preferences(prefs):
    """保存偏好数据到文件"""
    with open(PREFS_PATH, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)


# --- 历史记录 ---

def record_order(dish_name, restaurant_name, dish_type=""):
    """记录一次成功的点餐"""
    prefs = load_preferences()
    entry = {
        "dish": dish_name,
        "restaurant": restaurant_name,
        "type": dish_type,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    prefs["order_history"].append(entry)
    # 保留最近 200 条记录
    if len(prefs["order_history"]) > 200:
        prefs["order_history"] = prefs["order_history"][-200:]
    save_preferences(prefs)
    return entry


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


# --- 手动偏好 ---

def add_favorite(category, value):
    """添加喜欢的项目。category: restaurants/types/dishes"""
    prefs = load_preferences()
    key = f"favorite_{category}"
    if key not in prefs:
        return False
    if value not in prefs[key]:
        prefs[key].append(value)
        save_preferences(prefs)
    return True


def add_disliked(category, value):
    """添加不喜欢的项目。category: restaurants/types/dishes"""
    prefs = load_preferences()
    key = f"disliked_{category}"
    if key not in prefs:
        return False
    if value not in prefs[key]:
        prefs[key].append(value)
        save_preferences(prefs)
    return True


def remove_favorite(category, value):
    """移除喜欢的项目"""
    prefs = load_preferences()
    key = f"favorite_{category}"
    if key in prefs and value in prefs[key]:
        prefs[key].remove(value)
        save_preferences(prefs)
        return True
    return False


def remove_disliked(category, value):
    """移除不喜欢的项目"""
    prefs = load_preferences()
    key = f"disliked_{category}"
    if key in prefs and value in prefs[key]:
        prefs[key].remove(value)
        save_preferences(prefs)
        return True
    return False


def get_all_preferences():
    """获取当前所有手动偏好"""
    prefs = load_preferences()
    return {
        "favorite_restaurants": prefs.get("favorite_restaurants", []),
        "disliked_restaurants": prefs.get("disliked_restaurants", []),
        "favorite_types": prefs.get("favorite_types", []),
        "disliked_types": prefs.get("disliked_types", []),
        "favorite_dishes": prefs.get("favorite_dishes", []),
        "disliked_dishes": prefs.get("disliked_dishes", []),
    }


# --- 智能评分 ---

def score_dish(dish_name, restaurant_name, prefs=None, stats=None):
    """
    为菜品计算偏好得分。
    分数越高越受欢迎，负分表示不喜欢（应被排除）。
    """
    if prefs is None:
        prefs = load_preferences()
    if stats is None:
        stats = get_history_stats()

    score = 0

    # 手动偏好（最强信号）
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

    # 历史频率（较弱信号，用于辅助）
    dish_freq = stats.get("dishes", {})
    rest_freq = stats.get("restaurants", {})

    if dish_name in dish_freq:
        score += min(dish_freq[dish_name], 10)  # 最高 +10
    if restaurant_name in rest_freq:
        score += min(rest_freq[restaurant_name], 5)  # 最高 +5

    return score


def filter_by_preference(dishes, min_score=0):
    """
    基于偏好评分筛选菜品。
    移除不喜欢的（负分），返回得分 >= min_score 的菜品（按分数降序）。
    """
    prefs = load_preferences()
    stats = get_history_stats()

    scored = []
    for dish in dishes:
        dish_name = dish.get("name", "")
        restaurant = dish.get("_restaurant", "")
        s = score_dish(dish_name, restaurant, prefs, stats)
        if s >= min_score:
            scored.append((s, dish))

    # 按得分降序排列
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored]


# --- 命令行界面 ---

def cli_main():
    """偏好管理命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="美餐偏好管理器")
    sub = parser.add_subparsers(dest="command")

    # 查看偏好
    sub.add_parser("show", help="查看当前偏好和历史统计")

    # 标记喜欢
    p_fav = sub.add_parser("like", help="标记为喜欢")
    p_fav.add_argument("category", choices=["restaurant", "type", "dish"],
                       help="类别：restaurant=餐厅, type=菜系类型, dish=菜品")
    p_fav.add_argument("value", help="要标记的名称")

    # 标记不喜欢
    p_dis = sub.add_parser("dislike", help="标记为不喜欢")
    p_dis.add_argument("category", choices=["restaurant", "type", "dish"],
                       help="类别：restaurant=餐厅, type=菜系类型, dish=菜品")
    p_dis.add_argument("value", help="要标记的名称")

    # 移除偏好
    p_rm = sub.add_parser("remove", help="移除一条偏好记录")
    p_rm.add_argument("kind", choices=["favorite", "disliked"],
                      help="偏好类型：favorite=喜欢, disliked=不喜欢")
    p_rm.add_argument("category", choices=["restaurants", "types", "dishes"],
                      help="类别：restaurants/types/dishes")
    p_rm.add_argument("value", help="要移除的名称")

    # 历史记录
    p_hist = sub.add_parser("history", help="查看点餐历史")
    p_hist.add_argument("-n", type=int, default=10, help="显示最近 N 条记录")

    args = parser.parse_args()

    if args.command == "show":
        prefs = get_all_preferences()
        stats = get_history_stats()
        print("=== 手动偏好 ===")
        print(f"  喜欢的餐厅：{', '.join(prefs['favorite_restaurants']) or '（无）'}")
        print(f"  不喜欢的餐厅：{', '.join(prefs['disliked_restaurants']) or '（无）'}")
        print(f"  喜欢的类型：{', '.join(prefs['favorite_types']) or '（无）'}")
        print(f"  不喜欢的类型：{', '.join(prefs['disliked_types']) or '（无）'}")
        print(f"  喜欢的菜品：{', '.join(prefs['favorite_dishes']) or '（无）'}")
        print(f"  不喜欢的菜品：{', '.join(prefs['disliked_dishes']) or '（无）'}")
        print(f"\n=== 历史统计（共 {stats.get('total_orders', 0)} 次点餐）===")
        if stats["restaurants"]:
            print("  常去餐厅：")
            for name, count in list(stats["restaurants"].items())[:5]:
                print(f"    {name}：{count} 次")
        if stats["dishes"]:
            print("  常点菜品：")
            for name, count in list(stats["dishes"].items())[:5]:
                print(f"    {name}：{count} 次")

    elif args.command == "like":
        cat = args.category + "s"  # restaurant -> restaurants
        add_favorite(cat, args.value)
        print(f"[OK] 已将「{args.value}」添加到喜欢的{cat}")

    elif args.command == "dislike":
        cat = args.category + "s"
        add_disliked(cat, args.value)
        print(f"[OK] 已将「{args.value}」添加到不喜欢的{cat}")

    elif args.command == "remove":
        if args.kind == "favorite":
            remove_favorite(args.category, args.value)
        else:
            remove_disliked(args.category, args.value)
        print(f"[OK] 已从{args.kind} {args.category}中移除「{args.value}」")

    elif args.command == "history":
        prefs = load_preferences()
        history = prefs["order_history"]
        recent = history[-args.n:] if history else []
        if not recent:
            print("暂无点餐历史。")
        else:
            print(f"--- 最近 {len(recent)} 次点餐 ---")
            for h in reversed(recent):
                print(f"  {h['date']} | {h.get('restaurant', '?')} | {h['dish']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    cli_main()
