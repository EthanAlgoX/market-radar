# 交易雷达 · Market Radar

本地运行的个人交易资讯网站。输入关键词，从公开新闻、财经 RSS、X、Reddit 收集信息；连接自己的账号后，独立整理关注内容和推荐信息。每条内容保留原链接，支持主题分类、筛选、阅读、收藏与导出。

## 启动

环境：macOS/Linux、Node.js 22.12+、[uv](https://docs.astral.sh/uv/getting-started/installation/)。Python 3.12 由 uv 管理。

```bash
git clone https://github.com/EthanAlgoX/market-radar.git
cd market-radar
./setup.sh    # 首次安装
./start.sh    # 或 npm start
```

浏览器打开 **http://localhost:8787**。macOS 可双击 `start.command`。停止时在终端按 `Ctrl+C`。

首次克隆后先运行 `./setup.sh`；安装完成后，日常使用只需启动。所有服务绑定本机 `127.0.0.1`。请使用 localhost / 127.0.0.1 访问，以便账号回调和浏览器来源校验正常工作。

开发模式：`npm run dev`，前端 http://localhost:5173，后端 8787；前后端均自动重载。

## 已实现

- 关键词跨源采集：Google News RSS 搜索、财经 RSS、X、Reddit；可选 Hacker News 和外部 RSSHub。
- 交易主题：宏观、加密货币、美股、港股、A 股、财经、黄金；支持中英文关键词及 `OR` 查询。
- 三个独立频道：关键词资讯、我的关注、为我推荐。同一帖子可以同时出现在多个频道。
- 关注信息不强制命中关键词；指定作者的投稿独立收录。
- 标题、作者、正文/摘录、发布时间、命中词、原链接和来源，SQLite 本地保存。
- 链接/平台 ID 去重，收藏、已读、本地文本筛选、排序和 JSON/CSV 导出。
- 来源失败逐项显示，部分来源失败时仍保存成功结果；未连接的账号不会显示成已连接。
- 可选自动刷新与兼容 API 的 AI 中文摘要。AI 默认关闭，无密钥也能使用原文摘录。
- 一键中文阅读：使用环境中的 DeepSeek Flash 翻译标题、摘要与已采集正文，缓存译文并保留原始内容。

## 连接 X

进入「来源与账号」→「在浏览器登录 X」。程序新建隔离浏览器窗口，由你直接在 X 完成登录；本站不收取 X 密码，也不读取已有浏览器个人资料。验证账号身份成功后，才标记已连接。

支持关键词搜索、本人 Following、For You、作者时间线、同步关注名单。同步名单后仍读取本人 Following，再补充作者投稿。可在「关键词与加工」编辑作者名单。采集有分页和条数上限，并非历史全量备份。

若浏览器登录不可用，可展开「使用已有登录会话」，导入你自己的 Cookie JSON（需要 `auth_token` 与 `ct0`）。会话过期、网络失败、平台限制会显示需检查；平台的非官方接口可能变化，Twikit 无法保证永久可用。断开连接可清除本机保存的会话。

## 连接 Reddit

需要已经获 Reddit API 访问权限的应用。前往 [Reddit 应用设置](https://www.reddit.com/prefs/apps)，将回调地址设为：

```text
http://localhost:8787/api/connections/reddit/callback
```

在本站填写 Client ID 和 Client Secret（installed app 可留空），点击「登录并授权 Reddit」。授权仅请求读取所需的 scopes，refresh token 加密保存于本机。

支持关键词搜索、订阅社区、作者投稿、账号 API 首页。同步订阅可以读取社区及 API 可见的用户订阅；API 并不能保证提供完整的网页关注名单。可在设置中补充作者用户名，主动收录其社区投稿。推荐频道使用 OAuth `best` 列表，与 Reddit 网页个性化推荐可能不同。

网站登录不等于获得 Reddit 开发者访问权限。真实个人账号连接需要你授权，项目开发验证未使用任何个人账号。

## 公开 RSS 与加工

页面右上角提供「一键切换中文」。点击后使用后端环境中的 DeepSeek Flash（`deepseek-flash`）翻译资讯标题、摘要和来源返回的全文；切换主题、搜索或加载更多时会继续翻译新增内容。模式会在浏览器保存，可随时点击「切回原文」。来源、作者、原链接和你输入的关键词保留原样。

译文单独缓存在本机，原始内容不改写。缓存绑定原文版本和模型，相同内容不会重复请求；失败时保留原文、明确标识并提供重试。长文本分片完整翻译，超出支持上限或结果被截断时不会保存不完整译文。

翻译配置来自环境变量 `DEEPSEEK_API_KEY`、`DEEPSEEK_API_BASE`（也支持 `DEEPSEEK_BASE_URL`）。密钥仅供后端使用，不返回浏览器。模型默认为 `deepseek-flash`，如需其他 Flash 名称可设置 `DEEPSEEK_FLASH_MODEL`。启动脚本也支持项目根目录的 `.env`；可参考 `.env.example`，终端已有变量优先。配置更新后需重启后端。

翻译会将对应资讯文本发送到你配置的 DeepSeek 服务。正文仅限来源实际返回的内容；链接外的整篇文章不在本站自动抓取或翻译范围内。

默认来源为美联储、欧洲央行、CoinDesk、Yahoo Finance；「RSS 来源」可增删启用公开 RSS / Atom 地址。Google News 返回聚合跳转链接，点击可进入对应文章。各网站覆盖范围、更新频率和搜索语法不同，结果不是全网穷尽。

主题按文本规则分类，摘要默认是来源文本摘录。若启用 AI，可配置兼容 Chat Completions 的 API 地址、模型和密钥，然后在阅读面板点击生成摘要；对应文本会发送到你配置的服务。AI 不用于生成新闻、价格或虚构数据。

自动更新默认关闭。开启后只在本地服务运行期间生效，并分别收集关键词、已连接账号关注和推荐信息。

RSSHub 是可选外部服务，在账号页填实例地址后使用其 X 路由。`/twitter/home_latest` 与 `/twitter/home` 需要在 RSSHub 侧配置本人 X 会话。本项目不自动运行所有参考仓库。

## 文件与数据

```text
market-radar/
  frontend/             React + TypeScript + Vite
  backend/app/          FastAPI、采集器、SQLite、会话存储
  backend/tests/        离线采集与API/数据/安全回归测试
  backend/data/         本地数据库、加密凭据、密钥（不进入 Git）
  scripts/run.mjs       前后端启动与退出管理
  docs/REFERENCES.md    开源参考与实际依赖说明
  docs/REFERENCE_SNAPSHOTS.json  13 个参考仓库的精确版本清单
```

`RADAR_DATA_DIR` 可覆盖数据目录，需在启动前设置环境变量。密钥和密文保存在同一电脑，保护的是磁盘文件和误上传，不是抵御已控制本机的攻击者。迁移或备份时要同时保留密钥；不要把 `backend/data` 或个人会话放进公开仓库。

## 验证与接口

```bash
npm run check
npm run build
npm test
```

API 文档 http://localhost:8787/docs，健康检查 `/health`。导出入口 `/api/export?format=json` 或 `format=csv`。接口限制本机 Host 和来源，公开 RSS 请求校验地址和重定向，不允许访问私网；显式配置的本机 RSSHub 例外。

真实公开源已联网验证。X / Reddit 连接、分页、授权、断开和错误处理以离线模拟验证；实际账号连通性需要授权后验证。

参考仓库、固定版本和许可证详见 [docs/REFERENCES.md](docs/REFERENCES.md)。参考源码在开发时单独保存，不随本仓库上传，也不需要下载它们来运行本项目。本项目使用 Twikit / PRAW 等库实现自己的采集层；没有把 AGPL/GPL 参考平台的整套代码合并进来。
