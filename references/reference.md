# 配置参考

## 配置文件位置

`~/.meican-order.json`

## 完整配置示例

```json
{
  "username": "zhangsan@company.com",
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
      "exclude": ["炸", "香辣"]
    },
    "dinner": {
      "restaurants": ["等你下班"],
      "exclude": ["炸", "香辣"]
    }
  }
}
```

## 字段详解

### username（必填）

美餐账号登录邮箱。

### password（必填）

美餐账号密码。

### address_keyword（可选）

按关键字匹配取餐地址。不同时段（早/午/晚）的地址 UID 不同，脚本会自动从同时段的历史订单中匹配正确的地址。

示例：
- `"5"` — 匹配包含 "5" 的地址（如"公司大厦5楼"）
- `""` — 使用第一个可用地址

### budget（可选）

分时段预算上限，单位为元。超出预算的菜品会被自动过滤。

```json
{
  "breakfast": 8,
  "lunch": 20,
  "dinner": 20
}
```

设为 `0` 表示不限制该时段预算。

### meals（可选）

分时段的餐厅偏好和排除词配置。时段划分：
- **breakfast**：目标用餐时间 < 10:00
- **lunch**：10:00 <= 目标时间 < 14:00
- **dinner**：目标时间 >= 14:00

每个时段支持两个子字段：

#### restaurants（餐厅偏好列表）

字符串数组，模糊匹配餐厅名称。配置后只从匹配的餐厅中选菜。

```json
"restaurants": ["东江", "沙县小吃", "小明当家"]
```

- 支持部分匹配（如 `"东江"` 可匹配 `"东江海南鸡饭(棠东店)"`）
- 留空 `[]` 或不配置则不限制餐厅

#### exclude（排除关键词列表）

字符串数组，菜名含任一关键词则被排除。

```json
"exclude": ["炸", "香辣", "泡面"]
```

- 精确子串匹配
- 留空 `[]` 或不配置则不排除

## 命令行参数

命令行参数可临时覆盖或补充配置：

| 参数 | 说明 | 示例 |
|------|------|------|
| `--date` | 目标日期（YYYY-MM-DD 或 +N） | `--date "+1"` |
| `--tab` | 时间段关键字 | `--tab "午餐"` |
| `--expect` | 包含关键字（\| 分隔） | `--expect "鸡\|牛"` |
| `--exclude` | 额外排除关键字（\| 分隔） | `--exclude "辣"` |
| `--address` | 取餐地址关键字 | `--address "公司楼层"` |
| `--no-prefs` | 禁用偏好评分筛选 | |
| `--list` | 仅列出菜品不下单 | |
| `--orders` | 查看已下订单 | |
| `--cancel` | 取消订单 | |
| `--reorder` | 取消并重新点 | |
| `--share` | 让餐：将已点的餐品让给他人取餐（详见 share-meal.md） | `--share --tab "午餐"` |
| `--wait-restaurant` | 等待指定餐厅出现 | `--wait-restaurant "麦当劳"` |
| `--wait-retry` | 等待餐厅最大重试次数 | `--wait-retry 10` |
| `--wait-interval` | 基准等待秒数 | `--wait-interval 300` |
| `--week` | 点下周整周所有餐 | `--week` |

注意：`--exclude` 是追加到分时段 `meals.*.exclude` 之上的额外排除，不会替换配置中的排除词。

## API 说明

脚本使用以下美餐 API：

| 接口 | 方法 | 用途 |
|------|------|------|
| `/account/directlogin` | POST | 登录（带 OAuth 凭证获取 bearer token） |
| `/preorder/api/v2.1/calendarItems/list` | GET | 获取可用时间段和订单详情 |
| `/preorder/api/v2.1/restaurants/list` | GET | 获取餐厅列表 |
| `/preorder/api/v2.1/restaurants/show` | GET | 获取菜品列表 |
| `/preorder/api/v2.1/orders/add` | POST | 提交订单 |
| `/forward/api/v2.1/orders/delete` | POST | 取消订单（需 OAuth 认证） |
| `/forward/api/v2.1/orders/closetShow` | GET | 获取订单柜门信息（需 OAuth 认证） |
| `/forward/api/v2.1/orders/openClosetBox` | POST | 打开智能餐柜柜门（需 OAuth 认证） |

### 注意事项

- 下单接口使用 POST 方法，参数放在 query string 中
- 取消订单使用 `/forward/` 路径，需要 bearer token + client_id/client_secret
- `targetTime` 参数传递 Python datetime 对象（通过 urlencode 自动转为字符串）
- 不同时段的 `corpAddressUniqueId` 不同（早/午/晚各有独立地址 UID）

