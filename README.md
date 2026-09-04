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

## 开发验证

```bash
uv run python -m unittest discover -s tests -v
```

回归测试使用模拟接口和终端，覆盖日期边界、稀疏筛选、分页去重与停滞、实时分类、空列表历史加载，以及各输出格式的正文保留。

## License

MIT

## Docker 每日归档

```bash
docker compose up -d --build
docker compose logs -f archive
```

默认北京时间（`Asia/Shanghai`）每天 **00:10** 归档前一天完整电报，保存到宿主机
`/Users/bing/workspace/economic-crisis/raw/telegram/YYYY/MM/YYYY-MM-DD.md`。
首次启动如果已过执行时间，立即归档昨天；否则等到 00:10。
成功日期记录在输出目录的 `.archive-last-success`，重启后从该日期逐日补档。
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
