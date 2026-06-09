# 让餐功能参考

## 概述

让餐（`--share`）是指将已点但不想吃的餐品，通过打开智能餐柜柜门的方式让给同事取餐。

## 使用方式

```bash
# 让午餐（自动检测当前时间窗口）
python <SKILL_DIR>/scripts/order_meal.py --share

# 指定让餐类型
python <SKILL_DIR>/scripts/order_meal.py --share --tab "午餐"
python <SKILL_DIR>/scripts/order_meal.py --share --tab "早餐"
python <SKILL_DIR>/scripts/order_meal.py --share --tab "晚餐"
```

## 时间窗口限制

让餐只能在以下时间段内执行：

| 餐类 | 让餐时间窗口 |
|------|-------------|
| 早餐 | 8:30 - 10:30 |
| 午餐 | 11:30 - 13:30 |
| 晚餐 | 17:30 - 19:30 |

不在时间窗口内时，脚本直接拒绝执行。

脚本还会进一步校验 `closetShow` API 返回的 `closetAvailableStartTime` 和 `closetAvailableEndTime`，确保柜门在当前时间可用。

## 流程

1. **校验时间窗口** — 当前时间必须在对应餐类的让餐时间范围内
2. **获取订单** — 查找当天对应餐类的已下单记录
3. **获取柜门信息** — 调用 `closetShow` API 获取 `closetId`、`boxNumber`、`closetCode` 等
4. **打开柜门** — 调用 `openClosetBox` API 打开对应柜门
5. **输出结果** — 输出菜品详情、柜号柜门号、取餐地点等结构化信息

## API 说明

### closetShow（获取柜门信息）

```
GET https://www.meican.com/forward/api/v2.1/orders/closetShow
    ?client_id=XXX&client_secret=XXX&uniqueId=<订单uniqueId>
```

认证方式：Bearer token + Clientid/Clientsecret headers

响应关键字段：
- `orderUniqueId` / `uniqueId` — 订单短ID（12位hex），用于 openClosetBox 的 orderId
- `orderDishInBoxList[].closet.closetId` — 智能柜ID
- `orderDishInBoxList[].closet.closetCode` — 柜号（如 "D2"）
- `orderDishInBoxList[].orderClosetDishList[].boxNumber` — 柜门号
- `orderDishInBoxList[].orderClosetDishList[].name` — 菜品名
- `orderDishInBoxList[].orderClosetDishList[].restaurantName` — 餐厅名
- `orderDishInBoxList[].orderClosetDishList[].userReceived` — 是否已取餐
- `pickUpLocation` — 取餐地点
- `isShut` — 柜门是否关闭
- `closetAvailableStartTime` / `closetAvailableEndTime` — 柜门可用时间

### openClosetBox（打开柜门）

```
POST https://www.meican.com/forward/api/v2.1/orders/openClosetBox
    ?client_id=XXX&client_secret=XXX
Content-Type: application/x-www-form-urlencoded

orderId=<orderUniqueId>
closetId=<closetId>
boxNumberList=<boxNumber>
```

认证方式：与 closetShow 相同（Bearer token + Clientid/Clientsecret headers）

## 通知目标

让餐通知可以发给：
- **飞书群** — 用户指定群名或 chat_id
- **飞书联系人** — 用户指定人名
- **默认群** — 用户不指定时，发送到默认让餐通知群（chat_id 由用户在使用时配置）

Agent 规范：
1. 用户指定了让餐对象（群名/人名）→ 发给指定对象
2. 用户未指定 → 发到默认让餐群（chat_id 由用户配置）
3. 如果指定的是人名而非群名，先用 `feishu_search_user` 查到 open_id，再用 `feishu_im_user_message` 发私聊

## 输出格式

### 人类可读输出

```
========================================
[让餐成功] 午餐
========================================
  菜品：示例菜品名
  餐厅：示例餐厅名
  价格：20.0元
  取餐地点：公司楼层取餐点
  柜号：D2 | 柜门：16

[提示] 柜门已打开，请及时取餐
```

### 结构化 JSON 输出（供 agent 解析推送飞书通知）

```
---SHARE_JSON---
{
  "meal_type": "lunch",
  "meal_cn": "午餐",
  "title": "公司午餐（前一晚23点截单）",
  "pickup_location": "公司楼层取餐点",
  "real_name": "用户名",
  "dishes": [
    {
      "dish_name": "示例菜品名",
      "restaurant": "示例餐厅名",
      "price": 20.0,
      "closet_code": "D2",
      "box_number": 16
    }
  ],
  "opened_boxes": [
    {
      "closet_code": "D2",
      "box_number": 16,
      "closet_id": 3320
    }
  ]
}
---END_SHARE_JSON---
```

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| 当前时间不在让餐时间窗口内 | 时间不对 | 在允许时间段内执行 |
| 今天没有订单 | 未点该餐 | 先点餐再让餐 |
| 餐品已被取走 | 已取餐 | 无法让餐 |
| 智能餐柜已关闭 | 柜门关闭 | 等柜门开放 |
| 当前时间不在柜门可用时间范围内 | 柜门未开放 | 等到柜门可用时间 |
| 订单无柜门信息 | 非智能餐柜配送 | 该订单不支持让餐 |
| 获取柜门信息失败 | API 错误 | 检查网络和账号状态 |
| 打开柜门失败 | API 错误 | 检查网络和账号状态 |

## Agent 推送飞书通知规范

当 `--share` 执行成功后，agent 应解析 `---SHARE_JSON---` 和 `---END_SHARE_JSON---` 之间的 JSON，然后推送飞书群通知。

通知群（默认）：默认让餐通知群（chat_id 由用户在使用时配置）

若用户指定了让餐对象（群名/人名），则发给指定对象；若未指定，发到默认群。

通知模板：

```
🍱 让餐通知

菜品：示例菜品名
餐厅：示例餐厅名
取餐地点：公司楼层取餐点
柜号：D2，柜门：16

柜门已打开，请尽快取餐！
```

注意：通知中应包含柜号和柜门号，这是取餐的关键信息。