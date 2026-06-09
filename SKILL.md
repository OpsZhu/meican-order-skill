---
name: meican-order
version: 1.0.0
description: 美餐(meican.com)自动点餐技能，当用户提到点餐、美餐、自动订餐、取消订单、重新点、让餐、让饭、送餐、送饭、转餐、转饭、别人取餐、帮忙取餐、管理点餐偏好、设置定时点餐、抢餐、抢订、配置定时任务时使用。支持分时段餐厅偏好、预算控制、智能偏好学习。包含关键字筛选、基于历史的智能推荐、手动标记喜好/不喜好、偏好范围内随机选择、取消订单、重新点餐、让餐、定时点餐等功能。首次配置后自动引导配置定时任务。
---

# 美餐自动点餐

## 概述

美餐(meican.com)企业订餐平台的自动点餐工具。通过逆向 API 实现完全自动化，直接由脚本独立执行，无需浏览器运行，零额外成本。

功能包括：
- 完整点餐流程（登录、浏览、筛选、下单）
- 分时段配置（早/午/晚餐独立设置餐厅偏好和排除词）
- 预算控制（按时段限制单餐价格）
- 取消订单、重新点餐（不满意可一键换）
- 基于历史的偏好学习
- 手动标记喜欢/不喜欢（菜品、餐厅、菜系类型）
- 智能筛选：在偏好范围内随机选择
- 按日期点餐（支持 `+N` 天格式）
- **让餐功能**（打开智能餐柜柜门，让给同事取餐，通知发飞书群/联系人）
- **首次配置引导定时任务**（安装后自动询问配置）
- 定时点餐（整周方案、每日方案、抢餐任务）

## 文档读者说明

本文档面向两类读者：

- **用户**：了解如何使用本技能进行点餐、管理偏好、配置定时任务
- **Agent（AI）**：了解如何正确执行本技能的自动化流程

Agent 执行规范以 `⚡ Agent 执行规范` 标注，用户可忽略这些技术性指引。

## 前置条件

- Python 3.6+
- 已安装 `requests` 和 `pytz` 包
- 美餐账号

安装依赖：
```bash
pip install requests pytz
```

## 配置

### 凭据存储（密码不存于配置文件）

脚本按以下**读取优先级**尝试获取密码：

1. **系统密钥环**（最高优先级）— 若 keyring 存有密码则直接使用
   - 需安装 `keyring` 包，运行 `--setup` 配置：
   ```bash
   pip install keyring
   python <SKILL_DIR>/scripts/order_meal.py --setup
   ```

2. **环境变量**（次优先级）— 若 keyring 无密码，读取环境变量
   ```bash
   # Windows
   set MEICAN_PASSWORD=your_password
   
   # Linux/Mac
   export MEICAN_PASSWORD=your_password
   ```

3. 若两者都没有 → 报错提示配置

**推荐使用 keyring**（安全且无需每次设置环境变量）。

**注意**：密码**禁止**写入配置文件 `~/.meican-order.json`，配置文件仅存储用户名和非敏感选项。

### 配置文件

配置文件位于 `~/.meican-order.json`（仅存储非敏感信息）：

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
    "breakfast": {
      "restaurants": ["回味美食店", "小霞包点"],
      "exclude": ["泡面", "杂粮", "韭菜"]
    },
    "lunch": {
      "restaurants": ["东江", "沙县小吃", "小明当家"],
      "exclude": ["炸", "香辣", "甜"]
    },
    "dinner": {
      "restaurants": ["等你下班"],
      "exclude": ["炸", "香辣"]
    }
  }
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| username | 是 | 美餐登录邮箱 |
| address_keyword | 否 | 按关键字匹配取餐地址（如楼层 "5"） |
| budget | 否 | 分时段预算上限（单位：元） |
| meals | 否 | 分时段配置（餐厅偏好、排除关键词） |

### meals 分时段配置

时段划分规则：
- `breakfast`：目标时间 < 10:00
- `lunch`：10:00 <= 目标时间 < 14:00
- `dinner`：目标时间 >= 14:00

每个时段可配置：
| 子字段 | 说明 |
|--------|------|
| restaurants | 偏好餐厅列表（模糊匹配，只从这些餐厅选菜） |
| exclude | 排除关键词列表（菜名含任一关键词则排除） |

## 使用流程

> **路径约定**：下文中 `<SKILL_DIR>` 表示本技能的安装基目录（即 SKILL.md 所在目录），由运行时环境自动提供，不要硬编码。

### 首次使用（必须引导配置）

如果配置文件 `~/.meican-order.json` 不存在或缺少必需字段，**必须引导用户逐步完成配置**。

#### 配置完整性检查

- **必需字段**：`username`, `address_keyword`, `budget`
- **可选字段**：`meals`（偏好配置）
- 缺失必需字段 → 进入首次引导流程
- 仅缺失可选字段 → 正常执行，提示建议配置偏好

#### 配置流程（分三阶段）

**阶段一：基本配置**
1. 账号信息：美餐登录邮箱和密码
2. 取餐地址：楼层/地址关键字
3. 预算设置：早/午/晚餐单餐预算上限

保存：密码存密钥环（`--setup`），其他写入配置文件。

**阶段二：偏好配置**
4. 早/午/晚餐偏好：餐厅列表 + 排除关键词

**阶段三：定时任务配置**
> **⚡ Agent 执行规范**：配置完成后主动询问定时任务需求。

5. 询问："是否需要配置定时点餐任务？"
   - A. 周日点整周（推荐）
   - B. 每日点次日
   - C. 抢餐任务
   - D. 暂不配置

6. 根据选择引导配置，详见 [定时任务配置详情](references/scheduled-tasks.md)

**注意**：不要跳过步骤，不要用默认值代替用户输入。中断后下次启动继续引导。

### 手动点餐

当用户要求点餐时：

1. **检查配置完整性** — 若 `~/.meican-order.json` 不存在或缺少必需字段则先执行首次引导
2. **执行脚本**：
```bash
python <SKILL_DIR>/scripts/order_meal.py --date "+1" --tab "午餐"
```
3. **向用户报告结果**

### 命令行参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--date` | 指定日期（YYYY-MM-DD 或 +N 天后） | `--date "+1"`, `--date "2026-05-15"` |
| `--tab` | 时间段关键字筛选 | `--tab "午餐"`, `--tab "早餐"` |
| `--expect` | 菜品必须包含的关键字（\| 分隔） | `--expect "鸡腿\|牛肉"` |
| `--exclude` | 额外排除关键字（\| 分隔） | `--exclude "辣\|炸"` |
| `--address` | 取餐地址关键字 | `--address "公司楼层"` |
| `--no-prefs` | 禁用偏好筛选 | `--no-prefs` |
| `--list` | 仅列出可选菜品（不下单） | `--list` |
| `--orders` | 查看已下的订单 | `--orders` |
| `--cancel` | 取消订单 | `--cancel` |
| `--reorder` | 取消当前订单并重新点餐 |
| `--share` | 让餐：将已点的餐品让给他人取餐（打开柜门） | `--reorder` |
| `--wait-restaurant` | 等待指定餐厅出现（模糊匹配） | `--wait-restaurant "麦当劳"` |
| `--wait-retry` | 等待餐厅最大重试次数（默认10） | `--wait-retry 15` |
| `--wait-interval` | 基准等待秒数（默认300，实际随机300-600） | `--wait-interval 300` |
| `--week` | 点下周整周（周一到周五）所有餐 | `--week` |

**参数详细说明**：
- `--date "+N"`：相对日期（+1=明天，+2=后天）
- `--tab`：模糊匹配时段名称（如"午餐"可匹配"午餐时段"、"午市"）
- `--wait-restaurant`：等待餐厅开放后下单，详见 [等待餐厅详细说明](references/waiting-restaurant.md)
- `--week`：智能计算本周剩余或下周日期，详见 [整周点餐详细说明](references/weekly-order.md)

### 常用示例

```bash
# 点明天午餐（仅点午餐，不检查其他时段）
python <SKILL_DIR>/scripts/order_meal.py --date "+1" --tab "午餐"

# 点明天三餐（自动补单所有时段）
python <SKILL_DIR>/scripts/order_meal.py --date "+1"

# 点后天早餐
python <SKILL_DIR>/scripts/order_meal.py --date "+2" --tab "早餐"

# 列出可用菜品（带偏好指示）
python <SKILL_DIR>/scripts/order_meal.py --date "+1" --tab "午餐" --list

# 指定额外关键字点餐
python <SKILL_DIR>/scripts/order_meal.py --date "+1" --expect "鸡腿" --exclude "辣"

# 不使用偏好筛选
python <SKILL_DIR>/scripts/order_meal.py --date "+1" --no-prefs

# 整周点餐（周日执行，点下周周一到周五）
python <SKILL_DIR>/scripts/order_meal.py --week

# 整周点餐并排除特定菜品
python <SKILL_DIR>/scripts/order_meal.py --week --exclude "辣|炸"

# 仅列出本周剩余可点餐日期（不下单）
python <SKILL_DIR>/scripts/order_meal.py --week --list

# 等待餐厅开放后点餐
python <SKILL_DIR>/scripts/order_meal.py --date "+3" --tab "午餐" \
  --wait-restaurant "麦当劳"

# 等待餐厅开放后按关键字点餐
python <SKILL_DIR>/scripts/order_meal.py --date "+3" --tab "午餐" \
  --wait-restaurant "麦当劳" --expect "牛腩|鸡|排骨"

# 自定义等待参数（最多等15次，基准间隔5分钟，实际等待随机）
python <SKILL_DIR>/scripts/order_meal.py --date "+3" --tab "午餐" \
  --wait-restaurant "麦当劳" --wait-retry 15 --wait-interval 300
```

### 订单管理

```bash
# 查看已下的订单
python <SKILL_DIR>/scripts/order_meal.py --orders

# 取消明天午餐
python <SKILL_DIR>/scripts/order_meal.py --cancel --date "+1" --tab "午餐"

# 取消后重新随机选一个
python <SKILL_DIR>/scripts/order_meal.py --reorder --date "+1" --tab "午餐"

# 取消并按新条件重新点
python <SKILL_DIR>/scripts/order_meal.py --reorder --date "+1" --tab "早餐" --exclude "杂粮"
```

#### 重新点餐后偏好确认流程

> **⚡ Agent 执行规范**：当用户执行 `--reorder` 并成功完成点餐后，必须询问是否需要调整偏好。

**流程**：
1. 执行 `preferences.py show` 查看当前偏好
2. 询问："对新点的菜品满意吗？是否需要调整偏好配置？"
3. 根据用户选择执行偏好更新（like/dislike 命令）

**目的**：reorder 暗示不满意，是优化偏好的最佳时机，通过反馈循环提高推荐准确性。

### 让餐

将已点的餐品让给同事取餐——打开智能餐柜柜门，通知取餐人去拿。

**触发关键词**：让餐、让饭、送餐、送饭、转餐、转饭、别人取餐、帮忙取餐

#### 通知目标

让餐通知可以发给：
- **飞书群** — 用户指定群名或 chat_id
- **飞书联系人** — 用户指定人名
- **默认群** — 用户不指定时，发送到默认让餐通知群（chat_id 由用户在使用时配置）

> **⚡ Agent 执行规范**：让餐成功后，必须解析脚本输出的 `---SHARE_JSON---` / `---END_SHARE_JSON---` 之间的 JSON，然后按以下规则推送飞书通知：
>
> 1. 用户指定了让餐对象（群名/人名）→ 发给指定对象
> 2. 用户未指定 → 发到默认让餐群（chat_id 由用户配置）
> 3. 如果指定的是人名而非群名，先用 `feishu_search_user` 查到 open_id，再用 `feishu_im_user_message` 发私聊

```bash
# 让午餐（自动检测当前时间窗口）
python <SKILL_DIR>/scripts/order_meal.py --share

# 指定让餐类型
python <SKILL_DIR>/scripts/order_meal.py --share --tab "午餐"
python <SKILL_DIR>/scripts/order_meal.py --share --tab "晚餐"
```

#### 时间窗口限制

| 餐类 | 让餐时间 |
|------|----------|
| 早餐 | 8:30-10:30 |
| 午餐 | 11:30-13:30 |
| 晚餐 | 17:30-19:30 |

不在时间窗口内，脚本直接拒绝执行。

#### 飞书通知模板

```
🍱 让餐通知

菜品：示例菜品名
餐厅：示例餐厅名
取餐地点：公司楼层取餐点
柜号：D2，柜门：16

柜门已打开，请尽快取餐！
```

> 完整技术参考见 [references/share-meal.md](references/share-meal.md)

### 偏好管理

通过 `scripts/preferences.py` 管理偏好：

```bash
# 查看当前偏好和历史统计
python <SKILL_DIR>/scripts/preferences.py show

# 标记喜欢的餐厅
python <SKILL_DIR>/scripts/preferences.py like restaurant "湘菜馆"

# 标记不喜欢的菜系类型
python <SKILL_DIR>/scripts/preferences.py dislike type "麻辣"

# 标记喜欢的具体菜品
python <SKILL_DIR>/scripts/preferences.py like dish "番茄炒蛋"

# 移除偏好记录
python <SKILL_DIR>/scripts/preferences.py remove favorite restaurants "旧餐厅"

# 查看最近点餐历史
python <SKILL_DIR>/scripts/preferences.py history -n 20
```

### 筛选流程

脚本按以下顺序逐步筛选菜品：

1. **餐厅偏好** — 仅保留 `meals.{时段}.restaurants` 中匹配的餐厅菜品
2. **关键字排除** — 移除含 `meals.{时段}.exclude` + CLI `--exclude` 关键词的菜品
3. **关键字包含** — 如有 `--expect`，仅保留匹配菜品
4. **预算筛选** — 按 `budget.{时段}` 限价
5. **偏好评分** — 排除历史标记为不喜欢的，加权喜欢的
6. **随机选择** — 从剩余菜品中随机选取

### 偏好评分机制

评分采用**累加叠加**：

**不喜欢的项目（负分）**：
- 菜品：-100，餐厅：-50，类型：-30 → 总分 < 0 被排除

**喜欢的项目（加分）**：
- 菜品：+30，餐厅：+20，类型：+15

**历史记录**：
- 经常点的菜品：最高 +10，餐厅：最高 +5

**最终选择**：总分 >= 0 的菜品，**均等概率随机选取**（不按分数加权）

### 定时点餐

#### 方案对比

| 方案 | 执行频率 | 任务数量 | 单次点餐量 | 配置复杂度 | 适用场景 |
|------|---------|---------|-----------|-----------|---------|
| **方案一：周日点整周**（推荐） | 1次/周（周日） | 1个 | 下周5天×3餐=15餐 | **最低** | 提前规划整周餐食 |
| **方案二：每日点次日** | 5次/周（周一到周四+周日） | 1个（多触发器） | 1天×3餐=3餐 | 中等 | 每日动态调整偏好 |
| **方案三：抢餐任务** | 按需配置 | 1个 | 按需 | 中等 | 等待特定餐厅开放 |

> **详细配置说明**：[定时任务配置详情](references/scheduled-tasks.md)

#### 方案一：周日点整周（推荐）

> **⚠️ 强制约束**：**严禁直接使用示例时间（如 19:47、19:35）**。
> 必须由 Agent 动态生成 0-120 的随机整数，加到 19:00 计算出实际执行时间。

**Cron 配置**：
```cron
# 周日 {随机HH:MM} 点下周整周（时间由 Agent 配置时随机生成）
MM HH * * 0 python <SKILL_DIR>/scripts/order_meal.py --week
```

**Windows 任务计划程序**：
```
程序：python
参数：<SKILL_DIR>\scripts\order_meal.py --week
触发器：每周日 {随机HH:MM}（时间由 Agent 配置时随机生成）
```

> **⚡ Agent 执行规范**：生成 0-120 的随机分钟数，换算为 HH:MM 格式。

#### 方案二：每日点次日

> **⚠️ 强制约束**：**严禁直接使用示例时间（如 19:47、19:35）**。
> 必须由 Agent 动态生成 0-120 的随机整数，加到 19:00 计算出实际执行时间。

**Cron 配置**：
```cron
# 周一、二、三、四、日 {随机HH:MM} 点次日三餐（时间由 Agent 配置时随机生成）
MM HH * * 1-4,0 python <SKILL_DIR>/scripts/order_meal.py --date "+1"
```

**Windows 任务计划程序**：
```
程序：python
参数：<SKILL_DIR>\scripts\order_meal.py --date "+1"
触发器：每周一、二、三、四、日 {随机HH:MM}（时间由 Agent 配置时随机生成）
```

> **⚡ Agent 执行规范**：生成 0-120 的随机分钟数，换算为 HH:MM 格式。注意：周五、周六不执行。

#### 方案三：抢餐任务

**触发关键词**：`抢餐`、`抢订`、`等待餐厅`、`开放时间不确定`

**配置示例**：
```cron
# 周六 12:00 抢周四午餐（麦当劳）
0 12 * * 6 python <SKILL_DIR>/scripts/order_meal.py --date "+3" --tab "午餐" \
  --wait-restaurant "麦当劳"
```

> **⚡ Agent 执行规范**：询问必要信息（餐厅、时间、目标日期），生成配置。详见 [等待餐厅详细说明](references/waiting-restaurant.md)。

#### 已下单检查机制

- **无 --tab**：检查所有时段，仅补单未下单的
- **有 --tab**：仅检查指定时段
- 特殊日期自动跳过不可用时段（如周五无早餐）

---

**完整配置步骤、参数说明、Timeout 建议** → [定时任务配置详情](references/scheduled-tasks.md)

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| 登录失败 | 账号密码错误 | 检查配置文件中的 username/password |
| 无可用时间段 | 不在点餐时间或日期无可订 | 确认目标日期有可用时间段 |
| 无匹配菜品 | 筛选条件过严 | 放宽餐厅/关键字/预算，或使用 `--no-prefs` |
| 下单失败 | 地址错误或时间段过期 | 检查 address_keyword 是否匹配 |
| 取消订单失败 | 已过取消时限 | 检查是否在截止时间前 |
| 没有可取消的订单 | 指定日期无已下订单 | 使用 `--orders` 确认订单状态 |

## 脚本说明

- `scripts/order_meal.py` — 主点餐脚本（集成偏好系统）
- `scripts/preferences.py` — 偏好管理（历史记录、喜好标记）
- 配置文件：`~/.meican-order.json`
- 偏好数据：`~/.meican-preferences.json`（首次使用自动创建）

配置详情参见 [references/reference.md](references/reference.md)。
