# Market Radar：开源项目复核与采集改进评估

核查日期：2026-10-02。项目源码基线：`0cb615bcc016d1964d7ada78ded799ad84eee19c`。

本报告记录 0.2 开发前的评估基线；部分建议现已实现。当前功能和仍存在的限制见 [0.2 升级说明](UPGRADE_0_2.md)，本文保留原评估时的结论。

**建议保留现有网站，以 Twikit、PRAW 和 RSS 为采集基础，优先补齐可靠采集、财经来源和讨论上下文。** 最值得借鉴的是 Harken 的增量游标、Social Monitor 的来源契约与评论树、WorldMonitor 的财经目录与事件聚类、OpenMagpie 的采集与语义判断分离。没有发现一个项目可以直接完整替代 Market Radar，同时满足跨平台关键词、本人关注和本人推荐三种需求。

本轮重新检索了 GitHub，阅读了此前 13 个参考仓库及新增候选的关键源码、官方协议和文档，并对少量公开接口做了探测。下文区分三种证据：**源码已实现、官方文档支持、本次公开接口实测**。没有登录个人账号或调用收费 API；X/Reddit 的本人关注及推荐流仍需真实账号逐端点验收。本报告中的改进均为建议，尚未修改运行代码。

## 1. 推荐组合与接入顺序

| 层次 | 推荐组件 | 接入方式 | 目的 |
| --- | --- | --- | --- |
| 现有网站 | FastAPI + SQLite + React | 保留 | 继续统一检索、阅读、收藏、原文跳转和中文翻译 |
| X | Twikit；可选 twscrape / 浏览器后备 | 小型 Python adapter；浏览器独立任务 | Twikit 负责本人 Following/For You；twscrape 补搜索和作者采集，不替代本人首页 |
| Reddit | PRAW，必要时迁 Async PRAW | 直接包依赖，二者择一 | OAuth 首页、订阅社区、作者、搜索；补评论树与外部文章链接 |
| 财经公开来源 | 官方 RSS、TradingView RSS、按需 RSSHub | 现有 RSS adapter + 可选独立 RSSHub | 扩展宏观、美股、港股、A 股、黄金和加密市场覆盖 |
| 新增个人来源 | Bluesky / Telegram；YouTube 频道 | 按需求增加 adapter | 作者、所选信息流、交易频道、订阅视频；明确各自授权范围 |
| 采集机制 | Harken + Social Monitor 的设计 | 在现有栈内独立实现 | 持久游标、失败重试、限流、部分成功、评论与溯源 |
| 内容加工 | OpenMagpie + Freed + WorldMonitor 的设计 | 异步加工层 | 相关性排序、个人偏好、同一事件多来源整理 |

当前单用户本地应用适合先用 SQLite 做任务状态、租约和 checkpoint，无需立即部署所有候选的完整服务。以下 P0/P1/P2 是本项目的建议实施优先级，不是上游成熟度认证。

## 2. 此前 13 个项目逐项复核

| 项目 | 已确认的价值 | 应用于 Market Radar 的方式 | 主要边界 | 结论 |
| --- | --- | --- | --- | --- |
| [Twikit](https://github.com/d60/twikit) · MIT | 搜索、作者帖、分页；`get_timeline()` 为 For You，`get_latest_timeline()` 为 Following | 保留现有依赖，完善限流、游标、部分失败和会话健康 | 非官方网页协议；核心协议文件最后更新在 2025 年，较新的仓库提交主要改 README；有实现不等于现在能采通 | **直接使用，P0 加固** |
| [PRAW](https://github.com/praw-dev/praw) · BSD-2-Clause | Reddit OAuth、投稿、作者、订阅、Best/New、评论树、Listing 分页 | 保留依赖，先补内容和预算；当前 `<8`，升级需兼容验证 | SDK 不代替 Data API 审批；API Best 与网页 Home 推荐完全一致未验证 | **直接使用，P0 加固** |
| [Async PRAW](https://github.com/praw-dev/asyncpraw) · BSD-2-Clause | 同类 API 的原生异步客户端 | 并发与取消需求明确后替换 PRAW | 不会额外获得推荐或历史访问能力；不必同时维护两套 | **可选迁移，P1** |
| [RSSHub](https://github.com/DIYgod/RSSHub) · AGPL-3.0 | 非 RSS 网站转 feed；财经快讯、搜索、公告、账号时间线等具体路由 | 可选独立服务，通过 RSS 接入 | 不同路由有 Cookie、浏览器、第三方服务等要求；本人 X 首页需隔离本人会话 | **优先外接，P1** |
| [RSS-Bridge](https://github.com/RSS-Bridge/rss-bridge) · Unlicense | 按 bridge 转换公开网站、社区和作者到 RSS | RSSHub 缺少对应网站时再启用 | 用户页不等于本人关注首页；逐 bridge 核实，不能把菜单数量当可用覆盖率 | **补充旁路，P2** |
| [FreshRSS](https://github.com/FreshRSS/FreshRSS) · AGPL-3.0 | 成熟 RSS 阅读、条件请求、逐 feed 全文规则、过滤与标记 | 借鉴缓存、身份与阅读交互 | 本身不能提供 X/Reddit 本人推荐；换整套阅读器收益有限 | **设计参考** |
| [TrendRadar](https://github.com/sansan0/TrendRadar) · GPL-3.0 | 热榜、RSS、GUID 优先入库、时效配置、相似标题聚合 | 借鉴来源身份与多源聚合输出 | 热榜筛选不是全站搜索；标题相似不等于跨语言事件；RSS 抓取本身仍普通 GET | **设计参考** |
| [NewsNow](https://github.com/newsnext/newsnow) · MIT | 多来源热榜与财经 adapter；金十原链接构造、见闻快讯等 | 精选 adapter 思路与目录，转成本项目适配器 | 雪球 adapter 是热门股票，非用户帖子；README 宣布 NewsNext 并停止接收贡献 | **财经源参考，P1** |
| [Harken](https://github.com/VladUZH/harken) · MIT | Python/SQLite；incremental/backfill 游标、retry、来源失败隔离 | 优先借鉴提交后推进 checkpoint、增量/历史分离、错误分类 | 主题提取主要是词簇，不能称跨语言语义事件聚类；其通知队列不等于采集 worker 队列 | **最贴近当前栈，P0** |
| [Social Monitor](https://github.com/777genius/social-monitor) · Apache-2.0 | provider 能力与错误契约、扫描租约、持久重试、来源投影、评论关系 | 借鉴小接口与数据模型，不搬整套多租户平台 | NestJS/Flutter/数据库/队列部署较重；X 依赖私有 collector，Telegram 尚未接通 | **架构参考，P0/P1** |
| [OpenMagpie](https://github.com/obris-dev/openmagpie) · 根 Apache-2.0，`ee/` 另有条款 | Feed 拉取一次供多个 Watch；watermark/lease；语义 gate/action chain | 采集与加工分开，保存原始项后异步评分 | 主要 CLI/log/webhook；当前 Reddit 路径为公共社区 RSS，不能替本人 OAuth 首页 | **加工参考，P1/P2** |
| [x-summary](https://github.com/barbieri/x-summary) · GPL-3.0 | 隔离浏览器采本人 Following/For You 和作者页、摘要 | 借鉴页面解析与会话流程，必要时独立 CLI 旁路 | 不是多源平台；For You 非时间序，遇旧帖停止会漏后续新帖 | **浏览器后备，P1** |
| [Freed](https://github.com/freed-project/freed) · MIT | 内容规范化、媒体类型、作者偏好、时效/互动排序、后台语义任务 | 借鉴数据结构、可解释排序与阅读体验 | 当前 X 执行路径只取 Following，默认 20 条且无分页；端点定义不代表 For You 接通 | **产品/加工参考** |

这 13 个参考快照保存在 workspace 的 reference 目录。运行依赖与参考项目的区别、完整 commit 和许可证链接见仓库现有 `docs/REFERENCES.md` 与 `docs/REFERENCE_SNAPSHOTS.json`。本轮没有安装这些完整平台，也没有将它们的源码整体并入应用。

### 2.1 最值得先借鉴的具体机制

**Harken：可靠增量采集。** `fetch_page(query, limit, cursor, since)` 统一分页，SQLite 分别保存增量和历史补采状态；写入条目后才推进游标，失败不推进。网络错误、429、5xx 才有界重试。Market Radar 可以采用同样契约，避免每次重新抓首屏和停机后缺口。[Source 契约](https://github.com/VladUZH/harken/blob/d0710a427dbbe712594ef3a6c25112e1d14cc027/src/harken/sources/base.py)、[pipeline](https://github.com/VladUZH/harken/blob/d0710a427dbbe712594ef3a6c25112e1d14cc027/src/harken/pipeline.py)、[游标存储](https://github.com/VladUZH/harken/blob/d0710a427dbbe712594ef3a6c25112e1d14cc027/src/harken/store.py)。

**Social Monitor：来源能力和讨论关系。** 将账号绑定校验、扫描计划、分页、可重试错误、限流 reset 与评论树显式建模。对本项目，最有用的是 `CollectPage(items, next_cursor, warnings)`、来源观察记录和 `root/parent/depth` 评论关系。其 feature-status 明确区分 beta、私有依赖和尚未实现项。[Provider 接口](https://github.com/777genius/social-monitor/blob/1bea3dca70bbfbfe15d103ee78fd70715c9204e0/libs/ingestion/ports/source-provider.port.ts)、[扫描执行](https://github.com/777genius/social-monitor/blob/1bea3dca70bbfbfe15d103ee78fd70715c9204e0/libs/ingestion/features/execute-scan/execute-scan.use-case.ts)、[评论模型](https://github.com/777genius/social-monitor/blob/1bea3dca70bbfbfe15d103ee78fd70715c9204e0/libs/ingestion/adapters/source/reddit/reddit-comment-source-support.ts)、[功能状态](https://github.com/777genius/social-monitor/blob/1bea3dca70bbfbfe15d103ee78fd70715c9204e0/docs/reference/feature-status.md)。

**OpenMagpie：先采集，再判断相关性。** 共用 feed 减少重复采集网络请求，各主题的语义判断仍独立执行；如果本项目做模型缓存，缓存键必须包含主题/指令版本。我们的 Following/Recommended 应保留完整已取得的原始条目，语义分数只影响展示排序，不能因不含关键词而丢弃。[Feed polling](https://github.com/obris-dev/openmagpie/blob/27592ad8216e5ea0d6e0bd50727bbd10feb94cd1/apps/core/feeds/services/polling.py)、[语义 action](https://github.com/obris-dev/openmagpie/blob/27592ad8216e5ea0d6e0bd50727bbd10feb94cd1/apps/core/watches/actions/semantic_filter.py)。

**Freed：个人偏好和内容类型。** 保留文章/帖子/视频、作者、媒体与 publication 信息；排序结合时间衰减、作者偏好、主题、平台和对数互动量。这样能避免不同平台原始赞数直接竞争。它的 X 捕获边界必须按执行路径判断。[RSS normalization](https://github.com/freed-project/freed/blob/2bbd1fd8b7420129fc2a8799f81bad316daaac2e/packages/capture-rss/src/normalize.ts)、[ranking](https://github.com/freed-project/freed/blob/2bbd1fd8b7420129fc2a8799f81bad316daaac2e/packages/shared/src/ranking.ts)、[实际 X 捕获](https://github.com/freed-project/freed/blob/2bbd1fd8b7420129fc2a8799f81bad316daaac2e/packages/desktop/src/lib/x-capture.ts)。

**WorldMonitor：财经目录和事件视图。** 新增候选 [WorldMonitor](https://github.com/koala73/worldmonitor) 有 finance 分类、来源缓存/冷却、Jaccard 与可选 embedding 聚类，事件保留所有条目、独立出版方和首次/最近报道时间。适合借鉴“同一事件下的官方公告、媒体解释和社区讨论”。其财经目录中不少央行/媒体条目是 Google News 搜索代理，不能标成官方直连；本地旧源码包不能代表本次最新复核版本。根许可 AGPL-3.0。[财经目录](https://github.com/koala73/worldmonitor/blob/3c65f865246fcba8f20e90cf247bd5a11b345055/src/config/variants/finance.ts)、[聚类](https://github.com/koala73/worldmonitor/blob/3c65f865246fcba8f20e90cf247bd5a11b345055/src/services/clustering.ts)、[RSS/cache](https://github.com/koala73/worldmonitor/blob/3c65f865246fcba8f20e90cf247bd5a11b345055/src/services/rss.ts)。

FreshRSS 的 SimplePie 层有条件请求，全文按 feed 配置加载；TrendRadar 当前 GUID 优先去重与相似标题输出都值得参考，但它的 RSS fetcher 不能据此称为条件抓取。NewsNow 的雪球股票榜与 RSSHub 雪球本人时间线是不同能力。[FreshRSS HTTP 缓存](https://github.com/FreshRSS/FreshRSS/blob/a4dbc4240d8d0d62ab204ec7d3f68c4dd6e1cb38/lib/SimplePie/simplepie/src/SimplePie.php#L2073)、[TrendRadar GUID](https://github.com/sansan0/TrendRadar/blob/792bcc3928b1617bba09df34989fd5675c159b86/trendradar/crawler/rss/parser.py#L169)、[标题聚合](https://github.com/sansan0/TrendRadar/blob/792bcc3928b1617bba09df34989fd5675c159b86/mcp_server/tools/analytics.py#L2174)、[NewsNow 雪球](https://github.com/newsnext/newsnow/blob/0f95b2c998dffbfd2ddbc51b47b5809887dc6b97/server/sources/xueqiu.ts#L16)、[维护声明](https://github.com/newsnext/newsnow/blob/0f95b2c998dffbfd2ddbc51b47b5809887dc6b97/README.md#L125)。

## 3. 新候选与其他平台

| 项目 / 平台 | 支持的范围 | 不应承诺的范围 | 建议 |
| --- | --- | --- | --- |
| [twscrape](https://github.com/vladkens/twscrape) · MIT | X 搜索、作者帖、关系名单、列表；异步、账号会话、限流等待 | `following(user_id)` 是关注名单，不是本人 Following 帖子；没有 Home/For You 采集方法 | P1 搜索/作者后备；单账号设置总超时，无需账号池轮换 |
| [Nitter](https://github.com/zedeus/nitter) · AGPL-3.0 | 公共 X 前端与实例 RSS | 本人首页不是已完成能力；仓库 2026-09-11 已归档 | 不作为新核心；现有实例只作可失效旁路 |
| [MarshalX/atproto](https://github.com/MarshalX/atproto) · MIT / Bluesky | 协议支持搜索、作者 feed、本人 timeline、所选 feed generator | 未登录搜索不是所有服务都可用；timeline 不等于全部客户端的同一推荐流 | P1 候选；先作者/能力探测，再本人与自选 feed |
| [Mastodon.py](https://github.com/halcy/Mastodon.py) · MIT / Mastodon | 实例内作者、标签、OAuth home、stream | 全文搜索依赖实例后端与认证，不能称全 Fediverse 全站搜索 | P2，用户先选择实例和作者/标签 |
| [Telethon](https://github.com/LonamiWebs/Telethon) · MIT / Telegram | 本人所选频道、消息搜索、ID 增量和消息事件 | Bot API 不等于本人订阅与历史访问；没有统一的本人“推荐帖”接口 | P1 可选；GitHub 已迁 [Codeberg](https://codeberg.org/Lonami/Telethon)，先验证维护源与锁定版本 |
| [Google API Python Client](https://github.com/googleapis/google-api-python-client) · Apache-2.0 / YouTube | 关键词、频道、OAuth 本人订阅、上传列表 | 订阅不等于首页推荐；官方字幕下载受权限限制 | P1 频道 RSS，P2 API 与按需字幕 |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) · 源码 Unlicense | 可获取的视频 metadata 与公开字幕辅助 | 不能保证每个视频字幕存在或总可访问；不能代替 YouTube 本人推荐 | P2 辅助，仅按需抽取；无需批量下载视频 |
| [discord.py](https://github.com/Rapptz/discord.py) · MIT / Discord | 已授权 bot 所在服务器/频道消息与历史 | 不能仅凭本人登录读取所有加入的群；正文受 intent/权限控制 | P2，确有交易社群需求后接入 |
| [Stocktwits](https://api.stocktwits.com/developers) / 标的讨论 | 本轮 AAPL 公共 symbol JSON 返回 30 条消息，可做小型 adapter | 新应用注册暂停；本人 home/watchlist/recommend 未验证，不能承诺稳定 OAuth 合同 | P1 实验性公开标的源，保留原消息链接 |
| [Trafilatura](https://github.com/adbar/trafilatura) · Apache-2.0 / 新闻正文 | 静态 HTML 正文、metadata 抽取 | 不负责本人账号推荐，不保证付费/动态网页全文 | P1 优先正文工具，使用本项目安全网络层下载后解析 |
| [Crawl4AI](https://github.com/unclecode/crawl4ai) / JS 页面 | 浏览器驱动、HTML/Markdown 抽取 | 不能自动解决 X/Reddit 账号、审批和推荐接口 | P2 少数公开 JS 页面后备，资源/超时有界 |
| [Miniflux](https://github.com/miniflux/v2) · Apache-2.0 / RSS 服务 | 独立 RSS 订阅、条件请求、轮询、正文与 API | Go + PostgreSQL 新服务；仍不提供本人 X/Reddit 推荐 | 规模扩大时备选；当前独立部署收益低 |
| [market-intel](https://github.com/DaizeDong/market-intel) · MIT | 研究来源矩阵与任务路由 skill | 不是现成采集网站；README 列工具不等于内置 adapter | 仅借鉴选源与证据分级 |

Bluesky 的 `searchPosts` Lexicon 明示不同 provider 可能要求认证、cursor 不保证完整历史遍历；本人 timeline 与 feed generator 是不同端点。本轮作者 feed 成功、公开搜索失败，不能把协议支持写成无条件可用。[搜索协议](https://raw.githubusercontent.com/bluesky-social/atproto/main/lexicons/app/bsky/feed/searchPosts.json)、[timeline 协议](https://raw.githubusercontent.com/bluesky-social/atproto/main/lexicons/app/bsky/feed/getTimeline.json)、[feed 协议](https://raw.githubusercontent.com/bluesky-social/atproto/main/lexicons/app/bsky/feed/getFeed.json)。

Telegram 适合用户指定的交易频道，不默认遍历所有聊天；需要本人 API 配置与授权，保存频道/message ID 与可用原链接。GitHub 归档不意味着项目停止，README 指向 Codeberg；本轮未核实 Codeberg 的最新提交。[Telethon 授权](https://docs.telethon.dev/en/stable/basic/signing-in.html)、[消息 API](https://docs.telethon.dev/en/stable/modules/client.html)。

YouTube 可从频道 RSS 起步，再用 OAuth 同步本人订阅。官方字幕下载需要相应权限，应将公开字幕辅助与官方 API 区分。Mastodon 搜索限于所选实例可见内容；Discord 应走已授权 Bot 路线。[YouTube 订阅](https://developers.google.com/youtube/v3/docs/subscriptions/list)、[字幕权限](https://developers.google.com/youtube/v3/docs/captions/download)、[Mastodon 搜索](https://docs.joinmastodon.org/methods/search/)、[Discord Gateway](https://docs.discord.com/developers/events/gateway)。

GDELT DOC 2 可列为海外新闻发现候选，返回文章列表与原链接，不能当全文服务；本轮探测失败，接入前须验证当前访问、时间窗和吞吐。Hacker News 已有搜索 adapter，可沿官方 `kids/parent` 增加评论；它对技术/加密讨论更有用，不能替代完整财经来源。[GDELT 官方介绍](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)、[HN 官方 API](https://github.com/HackerNews/API)。

### 3.1 针对交易兴趣的财经来源包

优先把机构原公告、媒体解释和社区观点分层标记。以下路由是源码支持，除后续实测表列出的源站 feed 外，没有部署 RSSHub 作端到端验证。

| 需求 | 推荐来源与路由 | 条件与覆盖 |
| --- | --- | --- |
| 宏观 / 利率 / 黄金 | Fed 政策/讲话 RSS、ECB RSS；RSSHub `/gov/pbc/tradeAnnouncement`、`/gov/pbc/goutongjiaoliu`；见闻商品/外汇快讯 | Fed/ECB 可直接接；人民银行路由需要浏览器运行时；新闻 feed 不等于结构化经济指标 API |
| 美股 | CNBC Finance、SEC 公司/表单 Atom、TradingView 标的 RSS；Stocktwits 标的 JSON | SEC 本轮 403，待验证；TradingView 仅已验证 AAPL 公开观点；Stocktwits 仅公共消息 |
| 港股 | HKEX 官方发布；RSSHub 见闻 hk-stock、格隆汇、雪球作者/自选 | HKEX feed 是交易所公告，未验证每家上市公司全量披露；雪球本人需 Cookie |
| A 股 | RSSHub `/eastmoney/search/:keyword`、`/eastmoney/report/:category`、`/sse/disclosure/:query?`、`/szse/disclosure/listed/notice/:query?`、财联社电报 | 东方财富搜索仅首屏 10 条新闻；沪深公告窗口有限，PDF 链接不等于正文已解析 |
| 加密货币 | CoinDesk、X/Reddit 指定作者/社区、TradingView 标的观点；按需 Bluesky/Telegram | 新闻、作者、讨论分别保存；不假设所有标的/社区都有足够内容 |
| 跨市场快讯 | `/wallstreetcn/live/:category?/:score?`、`/cls/telegraph/:category?`、金十小型 JSON adapter | 见闻/财联社为栏目流；金十需补可验证的原详情链接，不能只展示无来源文本 |
| 本人中文投资作者 | `/xueqiu/timeline/:usergroup_id?`、`/xueqiu/user/:id/:type?` | timeline 需要 `XUEQIU_COOKIES` 与自建实例；作者等部分路由内部也用浏览器获取 Cookie |

具体源码：[东方财富搜索](https://github.com/DIYgod/RSSHub/blob/b0dce0ef9a009080a986334161a23eb0a8297afb/lib/routes/eastmoney/search/index.ts#L8)、[见闻快讯](https://github.com/DIYgod/RSSHub/blob/b0dce0ef9a009080a986334161a23eb0a8297afb/lib/routes/wallstreetcn/live.tsx#L19)、[财联社](https://github.com/DIYgod/RSSHub/blob/b0dce0ef9a009080a986334161a23eb0a8297afb/lib/routes/cls/telegraph.tsx#L35)、[雪球本人时间线](https://github.com/DIYgod/RSSHub/blob/b0dce0ef9a009080a986334161a23eb0a8297afb/lib/routes/xueqiu/timeline.ts#L10)、[沪市公告](https://github.com/DIYgod/RSSHub/blob/b0dce0ef9a009080a986334161a23eb0a8297afb/lib/routes/sse/disclosure.ts#L6)、[深市公告](https://github.com/DIYgod/RSSHub/blob/b0dce0ef9a009080a986334161a23eb0a8297afb/lib/routes/szse/disclosure/listed-notice.ts#L26)、[人民银行](https://github.com/DIYgod/RSSHub/blob/b0dce0ef9a009080a986334161a23eb0a8297afb/lib/routes/gov/pbc/trade-announcement.ts#L9)。本轮在线 RSSHub HEAD 已前进到 `25d2d42a7cd65ff8ab746e4610f74465340ccee8`；对比的七个关键路由文件与本地固定快照相同，未更新 reference 仓库。

有两个需要在接入时处理的具体问题：

- **本地财经 RSSHub 不能直接填入当前通用 RSS。** `public.py:80` 默认禁止 loopback，仅 X RSSHub 路径显式允许。应增加受信任的 RSSHub base/source 类型，只在对应配置范围放行本地地址，保留逐跳验证。[当前代码](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/connectors/public.py#L80)。
- **金十部分条目没有链接。** 本轮公开 JS 50 条和 RSSHub 上游 API 20 条的 `data.link` 全为空；RSSHub 路由直接使用它，而当前 parser 跳过非 HTTP 链接。NewsNow 按 ID 构造 `flash.jin10.com/detail/{id}` 可参考；构造后还应验证详情页与 ID 一致。这是源码与上游数据共同支持的缺口，未运行 RSSHub 端到端验证。[RSSHub 金十](https://github.com/DIYgod/RSSHub/blob/b0dce0ef9a009080a986334161a23eb0a8297afb/lib/routes/jin10/index.ts#L37)、[NewsNow 金十](https://github.com/newsnext/newsnow/blob/0f95b2c998dffbfd2ddbc51b47b5809887dc6b97/server/sources/jin10.ts#L22)。

### 3.2 本次公开接口实测

探测于 2026-10-02，北京时间约 22:50–23:10。成功仅反映本环境此时的响应，不是持续可用或完整采集保证；没有将这些新源配置进网站。

| 公开接口 | 结果 | 说明 |
| --- | --- | --- |
| [Fed monetary RSS](https://www.federalreserve.gov/feeds/press_monetary.xml) | 200 / 15 条；条件请求 304 / 0 bytes | 可验证官方原链接；证明 HTTP 缓存可减少重复下载 |
| [ECB press RSS](https://www.ecb.europa.eu/rss/press.html) | 200 / 15 条 | 官方发布，带 ETag |
| [HKEX releases RSS](https://www.hkex.com.hk/Services/RSS-Feeds/News-Releases?sc_lang=en) | 200 / 50 条 | 交易所本身公告 |
| [CNBC Finance RSS](https://www.cnbc.com/id/10000664/device/rss/rss.html) | 200 / 30 条 | 财经报道原链接 |
| [CoinDesk RSS](https://www.coindesk.com/arc/outboundfeeds/rss) | 308 跳转后 200 / 25 条 | 末尾斜杠应规范到实际 feed URL |
| [TradingView NASDAQ:AAPL RSS](https://www.tradingview.com/feed/?symbol=NASDAQ%3AAAPL) | 200 / 30 条 | 公开标的观点，非本人推荐 |
| [Stocktwits AAPL JSON](https://api.stocktwits.com/api/2/streams/symbol/AAPL.json) | 200 / 30 条 | 公共 symbol messages，非个人授权流 |
| [Bluesky 作者 feed](https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor=bsky.app&limit=3) | 200 / 3 条 | 公开作者动态 |
| [Mastodon Bitcoin 标签](https://mastodon.social/api/v1/timelines/tag/bitcoin?limit=3) | 200 / 3 条 | 此实例标签流 |
| SEC latest 10-K Atom | 403 | 官方文档支持，本环境未跑通 |
| Bluesky 未登录 bitcoin 搜索 | 403，非 JSON 响应 | 原因未确认，不能断言仅是认证问题 |
| GDELT bitcoin article list | HTTP 请求失败 | 未核实当前服务可用性 |
| 金十公开 JS / API | 200 / 50 与 20 条；`data.link` 均为空 | JS 样本另有 1 条 `source_link`，仍需可靠详情链接 fallback |

官方目录与访问要求：[Fed RSS](https://www.federalreserve.gov/feeds/feeds.htm)、[ECB RSS](https://www.ecb.europa.eu/home/html/rss.en.html)、[HKEX RSS](https://www.hkex.com.hk/services/rss-feeds?sc_lang=en)、[SEC RSS](https://www.sec.gov/about/rss-feeds)、[SEC 访问说明](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)。SEC 后续应使用真实联络信息的 User-Agent、缓存和温和请求频率，不能以反复重试当作 403 的解决方案。

## 4. 关键词、关注与推荐必须分别定义

| 平台 | 关键词发现 | 作者/订阅内容 | 本人算法推荐 | 本项目应显示的准确名称 |
| --- | --- | --- | --- | --- |
| X / Twikit | 搜索端点，分页与访问实际验证 | Following + 指定作者补采 | HomeTimeline/For You 代码路径存在，未认证实测 | 关键词 / 本人 Following / 本人 For You；注明 provider 和最后成功时间 |
| X / 官方 API | recent/all search，权限和费用不同 | reverse_chronological + 作者帖 | 本次公开标准端点目录未提供 For You | 官方搜索 / 本人时间序关注流 |
| Reddit / PRAW | 投稿搜索；当前限制过去一周 | Front New、订阅社区、作者投稿；评论需另接 | Front Best 已实现，网页同款未验证 | Reddit API Best；不称完整复刻网页推荐 |
| RSS / RSSHub | 在取得 feed 内过滤；部分站点有搜索路由 | 订阅 feed；个别本人路由需相应登录 | 普通 RSS 没有本人算法推荐 | 订阅 / 站内搜索路由 / feed 内关键词匹配 |
| Bluesky | searchPosts，按服务能力和授权 | 作者、本人的 timeline | 用户选择的 feed generator；范围按端点定义 | 作者 / timeline / 所选 feed |
| Telegram | 指定频道/可访问范围内搜索 | 用户选择的频道与消息 | 不承诺统一推荐 | 频道订阅 |
| YouTube | Data API 搜索 | 频道/RSS、本人的订阅 | 不承诺网页首页推荐 | 频道更新 / 本人订阅 |
| Mastodon / Discord | 实例搜索/标签；Discord 指定范围 | 实例 home / 授权 bot 频道 | 不承诺跨平台推荐复刻 | 实例动态 / 标签 / 社群频道 |

用户原需求中，“关注的人发了不含关键词的内容也要整理”应保持为硬约束。关键词搜索可以过滤；**Following 和 Recommended 必须先保存已取得的内容，相关性只用于排序或可选视图**。各渠道与账号的数据来源应保留，避免将关注作者列表、订阅社区、热门帖和算法推荐混称为“推荐”。

X 官方 API 是可选长期路线：官方时间线是关注账号时间序流，不含算法排序；当前按量费用需接入前核实 Console 与预算。Twikit、twscrape 和网页后备都有协议变化风险，限流配额也不能套用官方 API 的数值。[官方时间线](https://docs.x.com/x-api/posts/timelines/introduction)、[官方价格](https://docs.x.com/x-api/getting-started/pricing)。

Reddit 当前要求 Data API 访问预先审批；安装 PRAW、保存 token 不代表访问已经获批。应按官方 header 调度，保留删除/编辑回访与派生翻译失效路径。官方网页 Best 使用个性化推荐，但 API `front.best()` 与实际网页候选集合、推荐模块一致性未验证。[Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy)、[Data API Wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki)、[Home 推荐说明](https://support.reddithelp.com/hc/en-us/articles/4402284777364-What-are-home-feed-recommendations)、[PRAW Front](https://praw.readthedocs.io/en/stable/code_overview/reddit/front.html)。

## 5. 当前采集方式的改进空间

以下结论来自当前项目代码，行号对应报告基线。已经有精确 URL 去重、来源内部 ID、账号校验的部分路径、原链接和翻译缓存；改进建议不应被读作这些能力完全缺失。

| 优先级 | 现状与影响 | 建议 | 源码证据 |
| --- | --- | --- | --- |
| P0 | 所有采集任务共享内存锁，来源逐个等待；没有可恢复分页 checkpoint，重启后不能接续；慢来源拖累其余来源 | SQLite 持久任务/lease/checkpoint；来源有限并发、平台各自限流；失败不推进水位，成功页先落盘；区分增量与 backfill | [main.py](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/main.py#L214) |
| P0 | 采集层缺有界 429/5xx 重试、冷却和持久下次执行时间；RSS HTTP 只返回 bytes | 错误分类、Retry-After/backoff、部分成功；返回 status/final URL/ETag/Last-Modified，支持 304，标最后成功时间 | [security.py](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/security.py#L86) |
| P0 | 同一 query 直接发给不同平台；Google News 固定 US/en；RSS 只做 OR/逗号拆分后的子串匹配，中文词漏英文结果 | 主题→中英词组/别名/ticker→各 provider 查询编译；词边界与否定规则；记录真正发送的 query，不依靠显示翻译改善检索 | [public.py](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/connectors/public.py#L40)、[config.py](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/config.py#L12) |
| P0 | Reddit following 使用默认 limit=75、配置至少 25 作者且有社区时，去重前理论上限为 75 + 25×40 + 75 = 1,150 投稿；不是每次必达，也不是 HTTP 请求数；作者顺序可能不公平 | 单轮 post/请求/时间总预算，分桶配额、作者轮转、截断和 continuation 标记 | [reddit.py](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/connectors/reddit.py#L133) |
| P0 | Reddit token 存在即 connected；X 缓存 client 时验证可能过时；X 作者补采失败可使已取首页无法交付 | configured/verified/last_success/error 分开；低频真实验证；每端点健康；返回成功数据与 warnings | [reddit.py](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/connectors/reddit.py#L52)、[x.py](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/connectors/x.py#L500) |
| P1 | RSS 忽略 GUID/id；有 summary 时舍弃较长 content；去 HTML 丢段落，条目/正文有截断；新闻常只有标题摘要 | `feed_id + GUID/Atom id`，缺失才规范 URL fallback；保留结构化正文和截断标记；静态全文按需抽取，保留发布者、feed 与原文章链接 | [public.py](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/connectors/public.py#L19) |
| P1 | X/Reddit 主要存主帖、评论数量；Reddit 外链 `post.url` 未保留，HN 外部文章链接也未保存 | permalink 与 external_url 分开；有界评论/回复树，保留 parent/root、作者、正文、原链接、引用关系；热点或点击时加载 | [reddit.py](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/connectors/reddit.py#L148)、[x.py](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/connectors/x.py#L154) |
| P1 | 已有同 URL 去重，但跨源合并保留旧 source/ID、覆盖部分新 source_name/author/metadata，来源身份可能混合；URL 变体仍重复 | canonical content 与 source observations 分表，保存每次真实来源；保守去跟踪参数，原 URL 原样保留；事件层另建 | [store.py](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/store.py#L116) |
| P1 | 主题识别是子串，`gold` 命中 Goldman；相关性是命中词数/raw score，不同平台互动数不可直接比较 | 实体、ticker、语境规则；平台内互动归一化；分开相关性、时效、证据和作者偏好，给理由 | [store.py](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/store.py#L92) |
| P1 | 默认只有 4 个财经 RSS；CN/HK 默认信源薄；“所有来源”搜索构造列表没有 HN，虽然已有其 adapter | 精选官方/财经源包，主题与地区覆盖可见；入口与 SourceCapabilities 统一驱动，显示实际参与来源和覆盖停止原因 | [config.py](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/config.py#L26)、[App.tsx](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/frontend/src/App.tsx#L387) |
| P2 | 同一央行动作/财报/监管事件的公告、媒体和社交讨论并排堆积 | 相近时间 + 共同实体 + 事件类型聚类，保留独立来源、观点和时间线；数字/日期冲突避免强合并 | [store.py](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/store.py#L100) |

此外，X 当前关注名单默认取前 200、作者列表最多前 50，均不是“全量完整”。应保存轮转/分页状态并标截断；For You 不能用“遇旧帖立即停止”的时间序增量假设。PRAW 本身已经有 Listing 分页和基础限流，应在它之上补持久预算与 checkpoint，不重复造一套失效的限流层。[X adapter](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/connectors/x.py#L436)、[PRAW stream](https://praw.readthedocs.io/en/stable/code_overview/other/subredditstream.html)。

Reddit 已有外层 120 秒超时，但 `to_thread` 的同步线程不会因等待超时立即停止；内部需要取消/代际守卫和请求预算，或在异步迁移时明确取消行为。X RSSHub 后备首页使用服务端会话，当前未核验该会话是否为本人；应单独绑定并显示账号，不能把“RSSHub 有结果”当“本人身份已验证”。[Reddit 线程入口](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/connectors/reddit.py#L157)、[外层超时与 RSSHub 后备](https://github.com/EthanAlgoX/market-radar/blob/0cb615bcc016d1964d7ada78ded799ad84eee19c/backend/app/main.py#L240)。

当前 SSRF/DNS/重定向校验、请求字节上限、后端凭证保存、错误脱敏、原文保留、source hash 绑定翻译缓存都应保留。正文工具只解析安全下载得到的 HTML；浏览器后备另有显式访问范围和资源预算。翻译继续使用现有 DeepSeek flash；如扩展到查询词建议、相关性或事件摘要，应各自缓存与限额，不让模型判断阻塞来源采集。

## 6. 建议的数据与加工流程

```mermaid
flowchart LR
    A[主题与中英查询 / 作者与本人账号] --> B[来源能力与绑定]
    B --> C[持久任务 / 预算 / checkpoint]
    C --> D[X / Reddit / RSS / 其他 adapter]
    D --> E[原始条目与来源观察]
    E --> F[正文 / 评论 / 引用整理]
    F --> G[相关性与个人偏好]
    G --> H[事件组与多来源证据]
    H --> I[中文视图 / 原文 / 原链接]
```

建议分开保存：`source_bindings`（来源与账号）、`collection_runs/attempts/checkpoints`（执行与覆盖）、`contents`（稳定内容与版本）、`observations`（在哪个源/查询/渠道看到）、`conversation_units/references`（讨论关系）、`events/event_items`（事件关联）。翻译、摘要和相关性都是可失效的派生字段，记录内容 hash、profile/model/prompt 版本。

续页 cursor 与已完成采集的高水位必须分开：对 newest-first 来源，成功页落盘后可保存续页位置，但只有覆盖到旧边界或完整结束窗口，才能推进高水位。页数/条数/时间预算耗尽属于可续采截断，不能因为已经拿到最“新”的一页，就永久跳过尚未取得的较旧新帖。推荐流另用 seen-ID 窗口和有界页预算，不假设时间单调。

不要为了去重抹掉证据：同一文章在 Google News、RSS 和 Reddit 出现，是一篇文章的多个观察；Reddit/X 对文章的观点仍是独立帖子。同一话题也不必是同一事件。“黄金”“美联储”可以是长期主题，单次降息决定才是有时间、机构和参数的事件。

## 7. 实施阶段和验收

**第一阶段：可靠采集与查询，P0。** 统一 provider 请求/结果/错误契约；SQLite 持久任务与提交后 checkpoint；来源并发与每平台预算；限流重试、部分成功、来源健康；中英 query 编译；Reddit 总量预算与真实连接状态。验收应覆盖第 2 页限流、超时、进程重启、重复手动/自动任务、部分来源失败和预算截断；失败/未完成窗口不推进高水位，已成功内容仍交付，续页能恢复。关注作者的不含关键词帖必须保留。

**第二阶段：财经覆盖与阅读完整性，P1。** 添加精选官方 RSS、TradingView 和经过验证的 RSSHub 财经路由；完善 GUID/content、原文章链接、安全正文、有界评论；observations 溯源；按实际兴趣接 Bluesky 或 Telegram。每个来源标最近成功、实际条数、coverage/truncated，账号来源逐端点真实验收，不以 mock 测试替代。

**第三阶段：语义整理与扩展，P2。** 个人偏好、语义相关性、事件聚类；YouTube 字幕、Mastodon、Discord、JS 页面按需求加入。用人工标注中英财经样本评估相关性误报/漏报与事件误合并，尤其覆盖 Goldman/gold、同公司不同季度财报、相似央行公告和转发转载。原始关注流不能因语义 gate 减少，事件可拆分、模型失败仍能阅读原文。

只在多用户/多机器/规模需求确立后再引入 PostgreSQL 和独立分布式队列。当前最有价值的升级是**少漏、可恢复、可解释来源、读到正文和讨论**，随后才扩大平台数量。

## 8. 许可与复核范围

许可证名称来自根文件/官方仓库，用于记录来源，不代表已作具体分发行为的法律判定。项目尚未选定自身许可证；直接引入代码前应明确本项目许可证并核实相应文件、依赖及附加条款。GPL/AGPL 候选优先采用独立服务和独立实现的设计；旁路并不自动消除上游自身的许可义务。

本轮只新增研究文档；没有修改采集逻辑、账号配置或数据，没有测试真实个人首页，也没有将新报告推送到 GitHub。完整项目快照清单与固定 upstream 链接继续以现有 reference 文档为准。
