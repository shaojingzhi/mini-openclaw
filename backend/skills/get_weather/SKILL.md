---
name: get_weather
description: 获取指定城市（或经纬度）的实时天气信息。使用免费的 wttr.in 或 Open-Meteo API，不需要 API Key。
---

# get_weather — 查询实时天气

## 用途

当用户询问某个城市的天气（例如「北京今天天气怎么样？」、「上海现在多少度？」、「东京下雨吗？」），调用本技能。

本技能不依赖任何需要鉴权的天气服务，使用以下两个免费 API 之一即可：

- [`wttr.in`](https://wttr.in) — 直接返回人类可读的纯文本或 JSON，不需要 API Key。
- [`Open-Meteo`](https://api.open-meteo.com) — 返回结构化 JSON，不需要 API Key。

## 执行步骤

### 方案 A：使用 wttr.in（推荐，最简单）

1. 使用 `fetch_url` 工具请求：

   ```
   https://wttr.in/{城市名}?format=j1
   ```

   说明：
   - `{城市名}` 可以是英文（如 `Beijing`）或中文（如 `北京`），wttr.in 会自动识别。
   - `?format=j1` 让 wttr.in 返回结构化 JSON（而不是 ASCII 艺术），便于后续解析。
   - 如果用户只想要一句话天气，也可以省略 `?format=j1`，wttr.in 会直接返回一行天气描述。

2. 使用 `python_repl` 解析返回的 JSON，提取关键字段并生成中文摘要：

   ```python
   import json

   # 把 fetch_url 的输出（一段 JSON 文本）粘贴到 raw 变量
   raw = """<这里填 fetch_url 的返回值>"""
   data = json.loads(raw)

   current = data["current_condition"][0]
   nearest = data["nearest_area"][0]

   city = nearest["areaName"][0]["value"]
   country = nearest["country"][0]["value"]
   temp_c = current["temp_C"]
   feels_c = current["FeelsLikeC"]
   desc = current["lang_zh"][0]["value"] if "lang_zh" in current else current["weatherDesc"][0]["value"]
   humidity = current["humidity"]
   wind_kmph = current["windspeedKmph"]

   print(f"{city}（{country}）当前 {desc}，气温 {temp_c}°C（体感 {feels_c}°C），湿度 {humidity}%，风速 {wind_kmph} km/h。")
   ```

3. 把 `python_repl` 打印出来的那句中文返回给用户。

### 方案 B：使用 Open-Meteo（需要先查经纬度）

如果 wttr.in 不可用，回退到 Open-Meteo：

1. 用 `fetch_url` 调用地理编码：
   `https://geocoding-api.open-meteo.com/v1/search?name={城市名}&count=1&language=zh`
2. 从返回的 JSON 中取 `results[0].latitude` 和 `results[0].longitude`。
3. 用 `fetch_url` 调用实况天气：
   `https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m`
4. 用 `python_repl` 解析 JSON 并组装中文回复（weather_code 对应表见 Open-Meteo 文档）。

## 注意事项

- **必须先调用 `fetch_url` 获取数据，再用 `python_repl` 解析**。不要凭空编造天气数据。
- 城市名中有空格时，传入 URL 前需要 URL-encode（例如 `New York` → `New%20York`）。`python_repl` 里可以用 `urllib.parse.quote("城市名")` 处理。
- 如果两条路径都失败（网络不通、城市无法识别等），直接告诉用户「无法查询到该城市的天气，请确认城市名或稍后重试」，**不要伪造结果**。
- 回复中如果包含数字（温度、湿度、风速），务必保留原始单位（°C、%、km/h），避免误导。

## 输出格式建议

一句话中文摘要 + 可选的关键字段表。例如：

> 北京（China）当前晴，气温 22°C（体感 21°C），湿度 35%，风速 12 km/h。

如需更详细信息，可以追加：

- 风向、能见度、紫外线指数等字段（wttr.in 的 `current_condition` 都有）。
- 未来 3 天预报（wttr.in 返回的 `weather` 字段）。
