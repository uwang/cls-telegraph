# cls-telegraph

财联社电报 CLI 工具，在终端获取、筛选和实时监控 [财联社电报](https://www.cls.cn/telegraph) 快讯。

## 功能

- 获取最新电报，支持指定条数（无上限）
- 按等级 / 关键词 / 话题 / 股票 / 时间戳 / 分类多维度筛选
- 服务端分类过滤（加红 / 公司 / 看盘 / 港美股 / 基金 / 提醒）
- 终端彩色输出 + JSON 输出
- **全屏实时监控模式**（curses UI，类似 `htop` 的交互体验）

## 安装

需要 [uv](https://docs.astral.sh/uv/)。克隆后 `uv sync` 会自动创建虚拟环境、安装依赖并生成 `uv.lock`：

```bash
git clone https://github.com/InphinitiZ/cls-telegraph.git
cd cls-telegraph
uv sync
```

依赖：Python 3.8+，`requests`（由 uv 自动管理）

## 用法

### 基础获取

```bash
# 获取最新 20 条
uv run cls-telegraph

# 获取 50 条
uv run cls-telegraph -n 50

# JSON 输出（可管道到 jq）
uv run cls-telegraph -n 10 --json
```

### 筛选

```bash
# 按等级：A(加红/重大) B(重要) C(普通)
uv run cls-telegraph -l A

# 按服务端分类
uv run cls-telegraph -c 加红
uv run cls-telegraph -c 港美股

# 按关键词搜索（匹配标题和内容）
uv run cls-telegraph -k "原油"

# 按话题
uv run cls-telegraph -s "港股"

# 按关联股票（代码或名称）
uv run cls-telegraph --stock "ST西发"

# 指定时间范围（Unix 时间戳）
uv run cls-telegraph --since 1775140000 --before 1775145000

# 获取指定日期全天电报（默认取全天，可用 -n 截断）
uv run cls-telegraph --date 2026-09-01
uv run cls-telegraph --date 2026-09-01 -n 50

# 下载模式：将指定日期电报保存为 Markdown 文件（必须指定 --date）
# 默认 plain 风格：无标签、无股票、无等级标记
uv run cls-telegraph --download --date 2026-09-01
# markdown 风格：含等级标记、话题标签、关联股票
uv run cls-telegraph --download --date 2026-09-01 --format markdown
uv run cls-telegraph --download --date 2026-09-01 --output-dir ./downloads

# 归档模式：同下载，但按 年份/月份 目录层级存放（downloads/2026/09/2026-09-01.md）
uv run cls-telegraph --archive --date 2026-09-01 --output-dir ./downloads

# 组合使用
uv run cls-telegraph -n 30 -c 港美股 -k "IPO" --json
```

单次获取中的 `-n` 表示筛选后需要的条数。程序持续分页，直到数量满足、到达 `--since` 下界或接口返回空页；稀少关键词查询可能需要较长时间，可用 `--date` 或 `--since` 限定范围。日期查询直接从该日结束时间开始，`--since` / `--before` 包含对应秒。分页游标停滞时会报错退出，不写入下载文件。

### 实时监控模式

```bash
# 全屏监控，默认 15 秒刷新
uv run cls-telegraph -f

# 自定义刷新间隔
uv run cls-telegraph -f --interval 10

# 带筛选的监控
uv run cls-telegraph -f -l B
uv run cls-telegraph -f -c 加红
uv run cls-telegraph -f -k "原油"
```

**实时模式操作：**

| 按键 | 功能 |
|------|------|
| `j` / `k` / `↑` / `↓` | 逐行滚动 |
| 鼠标滚轮 | 3 行滚动 |
| `Page Up` / `Page Down` | 翻页 |
| `gg` | 回到顶部 |
| `G` | 跳到底部 |
| `/` | 搜索 |
| `n` / `N` | 下一个 / 上一个匹配 |
| `ESC` | 清除搜索 |
| `q` | 退出 |

- 新电报到达时显示 `★ NEW` 标记并自动回到顶部
- 在顶部按 `↑` 手动刷新
- 滚到底部按 `↓` 自动加载更多历史；列表为空或不足一屏时同样可用
- 历史游标按原始数据推进，没有匹配结果的页也可继续向前翻
- 指定分类或时间上界时使用 v1 API 刷新，其余情况使用 nodeapi

### 完整参数

```
uv run cls-telegraph -h

获取控制:
  -n, --count N          获取条数（默认 20；--date 模式下默认取全天）
  --date YYYY-MM-DD      获取指定日期（本地时区）的电报
  --since TIMESTAMP      获取该 Unix 时间戳之后的电报
  --before TIMESTAMP     获取该 Unix 时间戳之前的电报

筛选:
  -l, --level {A,B,C}    按等级筛选: A(加红) / B(重要) / C(普通)
  -k, --keyword TEXT     按关键词搜索（匹配标题和内容）
  -s, --subject TEXT     按话题分类筛选（如 '公告', '港股'）
  --stock CODE           按关联股票筛选（代码或名称）
  -c, --category NAME    服务端分类: 加红/公司/看盘/港美股/基金/提醒

输出:
  --json                 输出 JSON 格式
  --no-stock             不显示关联股票信息
  --content-limit N      正文最大显示字符数（默认 1000）
  --download             下载模式：保存指定日期电报为 Markdown 文件（必须配合 --date）
  --archive              归档模式：同 --download，但按 年份/月份 目录层级存放
  --format {plain,markdown}
                         下载模式内容风格（默认 plain：无标签/股票/等级标记）
  --output-dir DIR       下载模式输出目录（默认当前目录）

实时模式:
  -f, --follow           全屏实时监听新电报（q 退出）
  --interval N           监听刷新间隔秒数（默认 15）
```

## 输出示例

**终端模式：**

```
[2026-04-02 22:57:07] [B] ST西发董事长罗希失联 股价已连续两日跌停
  【ST西发董事长罗希失联...】
  📈 ST西发(sz000752) -5.01%
  🏷️  A股公告速递

[2026-04-02 22:52:02] [B] 小米集团调整子公司股东 雷军持股比例增加
  【小米集团调整子公司股东...】
  🏷️  港股动态, 小米汽车
```

等级颜色：A = 红色加粗，B = 黄色，C = 默认

**实时监控模式：**

```
 财联社电报 | 04月02日，星期三，23:25:04
─────────────────────────────────────────
 ★ NEW
[23:25:04] WTI原油期货涨幅再度扩大至10%
         🏷️  环球市场情报, 原油市场动态
                  ...
─────────────────────────────────────────
 📡 共 42 条 | 12s 后刷新 | ↑↓/jk翻页 /搜索 q退出
```

## 项目结构

```text
cls-telegraph/
├── cls_telegraph.py       # 单文件 CLI：抓取、筛选与输出
├── archive/
│   ├── __init__.py
│   ├── scheduler.py      # 每日调度、补档与归档文件写入
│   ├── storage.py        # SQLite 归档记录、通知队列与推送记录
│   └── bark.py           # Bark 配置、HTTP 请求与按设备重试
├── tests/
├── Dockerfile
├── compose.yaml
├── run-local.sh
├── .env.example
├── pyproject.toml
└── README.md
```

Docker 通过 `python -m archive.scheduler` 启动。归档模块随项目一起打包；
本地也可运行 `OUTPUT_DIR=./downloads uv run python -m archive.scheduler --status` 查看记录。
调度模块需要 Python 3.9+（使用标准库 `zoneinfo`），Docker 使用 Python 3.12。

## 开发验证

```bash
uv run python -m unittest discover -s tests -v
```

回归测试使用模拟接口和终端，覆盖日期边界、稀疏筛选、分页去重与停滞、实时分类、空列表历史加载，以及各输出格式的正文保留。

## License

MIT

## Docker 每日归档

本地一键构建、启动并查看日志：

```bash
./run-local.sh
```

脚本自动检查 Docker，缺少 `.env` 时从 `.env.example` 创建配置。
填写 Bark 设备 key 后再次运行即可应用配置。按 Ctrl+C 仅退出日志，容器继续运行。

也可以手动运行：

```bash
docker compose up -d --build
docker compose logs -f archive
```

默认北京时间（`Asia/Shanghai`）每天 **00:10** 归档前一天完整电报，保存到宿主机
`/Users/bing/workspace/economic-crisis/raw/telegram/YYYY/MM/YYYY-MM-DD.md`。
首次启动如果已过执行时间，立即归档昨天；否则等到 00:10。
成功日期与运行记录保存在输出目录的 `archive.sqlite3`，重启后从成功日期逐日补档。
旧版本的 `.archive-last-success` 在首次升级时自动导入，之后以数据库为准。
首次启动仅归档昨天，不自动扫描更早历史。失败每 5 分钟重试，单次任务最长 1 小时；
下载成功后才替换目标文件。日志可通过 Compose 查看，Docker 会轮转日志。
请保持 Docker 运行且电脑不休眠；停机期间不能执行，恢复后会依据成功记录补档。

可在项目 `.env` 中自定义（不提交此文件）：

```dotenv
ARCHIVE_TIME=00:10
ARCHIVE_OUTPUT_DIR=/Users/bing/workspace/economic-crisis/raw/telegram
```

修改后运行 `docker compose up -d`。停止服务用 `docker compose down`，归档文件保留。
Linux 上需要以宿主机用户写入时，可在服务中增加 `user: "1000:1000"` 并确保输出目录可写。

手动归档指定日期（不改变每日任务的成功记录）：

```bash
docker compose run --rm archive --archive --date 2026-08-30 --output-dir /data
```

其他 CLI 参数也可直接使用，例如 `docker compose run --rm archive -h`。

### Bark 通知与记录

复制 `.env.example` 为 `.env`，填写自己的设备 key（多个设备用逗号分隔）：

```dotenv
BARK_URL=https://api.day.app
BARK_DEVICE_KEYS=your-device-key
```

`BARK_URL` 只填服务基础地址，不包含设备 key 或 `/push`。运行
`docker compose up -d --build` 应用配置。未配置设备时继续归档，通知记录为 `disabled`；
以后启用 Bark 不补发这些已跳过的历史通知。

凌晨归档后只记录结果并将通知入队，**北京时间每天 08:00 起**发送待发 Bark 通知，
内容包含日期、条数、文件大小和容器内路径，分组为 `cls.archive`。
可用 `BARK_PUSH_TIME=08:00` 调整时间。成功、失败告警及重试均不会在当天该时间之前发送；
08:00 后完成的归档或恢复运行的服务会及时补发，仍沿用原有失败重试间隔。
同一归档日期首次失败时创建一条失败告警，后续失败只追加运行记录；恢复成功后创建成功通知，
尚未送达的失败告警标记为 `superseded`，避免恢复后再收到过期告警。

查看最近各 20 条归档、通知、设备状态和推送尝试：

```bash
docker compose run --rm archive --status
docker compose logs --tail=100 archive
```

完整记录在宿主机输出目录下的 `archive.sqlite3`，可用 SQLite 查看：

| 表 | 内容 |
| --- | --- |
| `archive_log` | 每次归档日期、开始/结束时间、状态、文件路径、字节数、条数、错误类型 |
| `notifications` | 通知内容与整体状态：pending/success/disabled/superseded |
| `deliveries` | 每台设备的送达状态与下次重试时间 |
| `push_log` | 每次 HTTP 推送的时间、耗时、结果、错误类型或 HTTP 状态码 |
| `meta` | 最后成功归档日期 |

时间字段使用 Unix 秒。设备在记录中只保存 SHA-256 标识，不保存完整 key；
网络错误只存异常类别，不写入可能含密钥的响应正文或异常文本。
任务被中断后，其 `running` 记录在重启时标记为 `interrupted`，随后重新归档。
归档完成与通知入队在同一数据库事务中提交，推送失败不回退归档进度。
同一输出目录通过文件锁限制为一个调度进程。

### 弱网重试

- v1 抓取每页默认最多尝试 `FETCH_RETRIES=10` 次，失败后随机等待 2–4 秒，
  重试当前分页游标；连接/读取超时分别为 5/15 秒。网络、JSON 或字段异常重试，合法空页正常结束。
- 整日归档失败默认 `ARCHIVE_RETRY_SECONDS=300` 秒后重试，单次归档最长一小时。
  下载完成后原子替换 Markdown；失败不会覆盖原有文件。
- Bark 使用复用连接的 Session，POST JSON 到 `/push`，连接/读取超时分别为 5/15 秒。
  每台设备每轮最多尝试 4 次，退避区间为 2–4、6–10、15–25 秒。
  必须 HTTP 200 且 JSON `code == 200` 才记录成功。
- Bark 当轮仍失败，默认 `BARK_RETRY_SECONDS=900` 秒后补发；每次尝试持久化记录。
  重启后只补发未成功设备。通知创建时固定设备集合，新增设备不接收旧通知；
  移除的设备保留待发状态，恢复配置后可继续补发。
- Bark 服务已接收但响应丢失时，重试可能产生重复通知；这是远端送达确认的不确定性。
  归档与推送在单进程中串行运行，长时间归档会延后待发通知。

以上运行记录和 Bark 通知适用于每日调度服务。直接传 CLI 参数的手动命令仍是单次下载，
不写入调度数据库、不发送 Bark，也不改变自动补档进度。
