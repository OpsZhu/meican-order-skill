# meican-order

美餐（meican.com）企业订餐平台自动点餐技能 / Skill。通过逆向 API 实现完全自动化(平台更新可能导致接口失效，切用且珍惜。注意限制调用频率和次数，避免短时间频繁调用影响商家正常服务)，无需浏览器，纯 Python 脚本独立运行。

## 功能

- 完整点餐流程：登录、浏览、筛选、下单
- 分时段配置：早 / 午 / 晚餐独立设置餐厅偏好和排除词
- 预算控制：按时段限制单餐价格上限
- 订单管理：查看订单、取消、重新点餐
- 偏好系统：基于点餐历史的智能推荐 + 手动标记喜欢 / 不喜欢
- 让餐功能：打开智能餐柜柜门，把已点的餐让给同事取
- 抢餐：等待指定餐厅开放后自动下单
- 整周点餐：周日一次性点下周整周（周一到周五），或周中补本周剩余
- 定时点餐：支持 cron / Windows 任务计划程序

## 前置条件

- Python 3.6+
- 美餐账号

```bash
pip install requests pytz keyring
```

`keyring` 可选，但强烈推荐——用于把密码安全存到操作系统密钥环（Windows 凭据管理器 / macOS 钥匙串 / Linux Secret Service）。

## 快速开始

### 1. 安全配置凭据

```bash
python scripts/order_meal.py --setup
```

按提示输入美餐邮箱和密码，密码会写入系统密钥环，账号写入 `~/.meican-order.json`。

### 2. 配置取餐地址和预算

编辑 `~/.meican-order.json`：

```json
{
  "username": "your_email@company.com",
  "address_keyword": "5",
  "budget": {
    "breakfast": 8,
    "lunch": 20,
    "dinner": 20
  },
  "meals": {
    "lunch": {
      "restaurants": ["东江", "沙县小吃"],
      "exclude": ["炸", "香辣"]
    }
  }
}
```

`address_keyword` 用于匹配取餐地址（如 `"5"` 匹配 "公司大厦5楼"）。`meals` 可选，按时段配置餐厅偏好与排除关键词。

### 3. 点餐

```bash
# 点明天午餐
python scripts/order_meal.py --date "+1" --tab "午餐"

# 点明天三餐
python scripts/order_meal.py --date "+1"

# 仅列出可选菜品
python scripts/order_meal.py --date "+1" --tab "午餐" --list

# 整周（周日执行点下周一到周五）
python scripts/order_meal.py --week
```

## 常用命令

| 操作 | 命令 |
|------|------|
| 列出菜品 | `--list` |
| 查看订单 | `--orders` |
| 取消订单 | `--cancel --date "+1" --tab "午餐"` |
| 重新点餐 | `--reorder --date "+1" --tab "午餐"` |
| 让餐 | `--share --tab "午餐"` |
| 抢餐 | `--wait-restaurant "麦当劳" --wait-retry 10` |

完整参数说明：`python scripts/order_meal.py --help`

## 偏好管理

```bash
# 查看当前偏好和历史统计
python scripts/preferences.py show

# 标记喜欢 / 不喜欢
python scripts/preferences.py like restaurant "湘菜馆"
python scripts/preferences.py dislike type "麻辣"

# 查看点餐历史
python scripts/preferences.py history -n 20
```

## 凭据存储

按读取优先级：

1. 系统密钥环（推荐，需 `pip install keyring` 后运行 `--setup`）
2. 环境变量 `MEICAN_USERNAME` / `MEICAN_PASSWORD`
3. 配置文件（不推荐，仅用于兼容）

密码不会写入配置文件。如果检测到配置文件中存在明文密码，且 `keyring` 可用，会自动迁移到密钥环。

## 文档

- [SKILL.md](SKILL.md) — 完整功能说明（用户 + Agent 双用途）
- [references/reference.md](references/reference.md) — 配置字段详解
- [references/scheduled-tasks.md](references/scheduled-tasks.md) — 定时任务配置
- [references/weekly-order.md](references/weekly-order.md) — 整周点餐说明
- [references/waiting-restaurant.md](references/waiting-restaurant.md) — 抢餐 / 等待餐厅
- [references/share-meal.md](references/share-meal.md) — 让餐功能详细说明

## 作为 Claude Code Skill 使用

本仓库符合 Claude Code Skill 规范（根目录有 `SKILL.md` frontmatter）。把整个仓库目录放到你的 skills 目录即可被 Claude Code 自动发现。Skill 会响应"点餐"、"让餐"、"抢餐"、"配置定时任务"等关键词。

## License

MIT
