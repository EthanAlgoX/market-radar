# 参考来源与实际复用清单

Market Radar 是独立实现的本地资讯聚合应用，核心运行路线是 **FastAPI + PRAW + Twikit**，并可接入 RSS。它没有启动 Social Monitor、Harken、FreshRSS 等完整上游平台，也不从开发时单独保存的参考快照导入这些平台的源码。

## 实际声明的运行依赖

以下清单来自 [backend/pyproject.toml](../backend/pyproject.toml)、[backend/requirements.txt](../backend/requirements.txt) 和 [frontend/package.json](../frontend/package.json)。它说明应用通过包管理器安装和调用的组件；不是 13 个参考仓库已部署的声明，也不是实时平台接入已验证的声明。

| 层 | 声明的包和版本范围 | 用途 |
| --- | --- | --- |
| 后端 API | `fastapi>=0.115,<1`、`uvicorn[standard]>=0.30,<1` | 提供本地接口与服务进程 |
| Reddit | `praw>=7.8,<8` | 官方 Reddit API 客户端；关键词/社区/作者采集及登录后的订阅首页 |
| X | `twikit>=2.3,<3` | X 登录会话客户端；关键词、作者、本人 For You/Following 时间线 |
| HTTP/RSS | `httpx>=0.27,<1`、`feedparser>=6,<7` | 请求外部服务和解析 RSS/Atom |
| 公开正文 | `trafilatura>=2.2,<3` | 用户按需读取可访问 HTML 文章时提取正文，保留原始链接与段落 |
| 凭证存储 | `cryptography>=44` | 本地凭证加密工具 |
| 浏览器集成 | `playwright>=1.50,<2` | 浏览器会话集成组件；安装包不代表已下载浏览器或已完成登录 |
| 前端 | `react=19.3.0`、`react-dom=19.3.0`、`lucide-react=1.49.0` | 独立开发的 React 界面与图标 |

前端构建工具另有 TypeScript `^6.0.0`、Vite `8.3.2`、`@vitejs/plugin-react` `6.1.1` 和 React 类型包；后端 `dev` 可选依赖声明 pytest 与 pytest-asyncio。SQLite 存储使用 Python 标准库，不作为独立下载平台。安装时解析出的具体包版本应以环境或 lockfile 为准，不能把下表的参考 commit 当成已安装包版本。

## 上游参考快照

开发时单独保存了 13 个参考仓库，完整 SHA、下载北京时间、原始 URL、下载状态和用途见 [REFERENCE_SNAPSHOTS.json](REFERENCE_SNAPSHOTS.json)。这些本地源码快照不随本仓库上传；下表链接指向上游对应的固定版本。每个快照都是 `--depth=1` 的上游默认分支克隆，保留 `.git` 与原许可证；本次全部下载成功，未安装它们的依赖，未修改它们的源码。运行本项目无需另外下载参考仓库。

| 上游仓库 | 本次快照的根许可证 | 默认分支与参考 commit | 与本项目的关系 |
| --- | --- | --- | --- |
| [rsshub](https://github.com/DIYgod/RSSHub) | [AGPL-3.0](https://github.com/DIYgod/RSSHub/blob/b0dce0ef9a009080a986334161a23eb0a8297afb/LICENSE) | `master` · `b0dce0ef9a00` | 可选外部 RSS 服务 |
| [praw](https://github.com/praw-dev/praw) | [BSD-2-Clause](https://github.com/praw-dev/praw/blob/718b90c75e0f8758d45db75e33b7d72e430d026a/LICENSE.txt) | `main` · `718b90c75e0f` | 包依赖：Reddit 客户端 |
| [asyncpraw](https://github.com/praw-dev/asyncpraw) | [BSD-2-Clause](https://github.com/praw-dev/asyncpraw/blob/5d60aa2bc82122a013bb9d0c63d206b22369e53d/LICENSE.txt) | `main` · `5d60aa2bc821` | 参考快照；未作为平台部署 |
| [social-monitor](https://github.com/777genius/social-monitor) | [Apache-2.0](https://github.com/777genius/social-monitor/blob/1bea3dca70bbfbfe15d103ee78fd70715c9204e0/LICENSE) | `main` · `1bea3dca70bb` | 参考快照；未作为平台部署 |
| [harken](https://github.com/VladUZH/harken) | [MIT](https://github.com/VladUZH/harken/blob/d0710a427dbbe712594ef3a6c25112e1d14cc027/LICENSE) | `main` · `d0710a427dbb` | 参考快照；未作为平台部署 |
| [rss-bridge](https://github.com/RSS-Bridge/rss-bridge) | [Unlicense](https://github.com/RSS-Bridge/rss-bridge/blob/cc8a6459b1f67066bd861b2f225f3aef12ea198d/UNLICENSE) | `master` · `cc8a6459b1f6` | 参考快照；未作为平台部署 |
| [freshrss](https://github.com/FreshRSS/FreshRSS) | [AGPL-3.0](https://github.com/FreshRSS/FreshRSS/blob/a4dbc4240d8d0d62ab204ec7d3f68c4dd6e1cb38/LICENSE.txt) | `edge` · `a4dbc4240d8d` | 参考快照；未作为平台部署 |
| [trendradar](https://github.com/sansan0/TrendRadar) | [GPL-3.0](https://github.com/sansan0/TrendRadar/blob/792bcc3928b1617bba09df34989fd5675c159b86/LICENSE) | `master` · `792bcc3928b1` | 参考快照；未作为平台部署 |
| [newsnow](https://github.com/newsnext/newsnow) | [MIT](https://github.com/newsnext/newsnow/blob/0f95b2c998dffbfd2ddbc51b47b5809887dc6b97/LICENSE) | `main` · `0f95b2c998df` | 参考快照；未作为平台部署 |
| [openmagpie](https://github.com/obris-dev/openmagpie) | [Apache-2.0](https://github.com/obris-dev/openmagpie/blob/27592ad8216e5ea0d6e0bd50727bbd10feb94cd1/LICENSE) | `main` · `27592ad8216e` | 参考快照；未作为平台部署 |
| [twikit](https://github.com/d60/twikit) | [MIT](https://github.com/d60/twikit/blob/c3b7220866f8582009fe2d1155b6fe92192a2711/LICENSE) | `main` · `c3b7220866f8` | 包依赖：X 客户端 |
| [x-summary](https://github.com/barbieri/x-summary) | [GPL-3.0](https://github.com/barbieri/x-summary/blob/dc7740f33767d675afc549cffaab4031f0775482/LICENSE) | `master` · `dc7740f33767` | 参考快照；未作为平台部署 |
| [freed](https://github.com/freed-project/freed) | [MIT](https://github.com/freed-project/freed/blob/2bbd1fd8b7420129fc2a8799f81bad316daaac2e/LICENSE) | `dev` · `2bbd1fd8b742` | 参考快照；未作为平台部署 |

## 具体参考了什么

- **PRAW**：使用已声明的安装包作为 Reddit 客户端。API 设计参考 `Reddit.subreddit(...).search(...)`、作者 submissions、`Reddit.front` 和用户订阅查询；账号授权与上游权限决定登录后读取范围。参考目录不是运行时导入路径。
- **Twikit**：使用已声明的安装包作为 X 客户端。上游 [client.py](https://github.com/d60/twikit/blob/c3b7220866f8582009fe2d1155b6fe92192a2711/twikit/client/client.py) 明确说明 `get_timeline()` 对应 Home → For You，`get_latest_timeline()` 对应 Home → Following，并提供 `search_tweet()`、作者查询与 Cookie 载入。应用自己的 adapter、过滤逻辑与界面是独立实现。
- **RSSHub**：作为可选独立 RSS 源，不是应用内嵌库。参考 `/twitter/keyword/:keyword`、`/twitter/user/:id`、`/twitter/home` 和 `/twitter/home_latest` 路由，以及保留原帖 URL 的输出结构。本项目直接用 Twikit 获取 X 数据时不依赖 RSSHub 服务。
- **Social Monitor / Harken**：参考多来源 adapter → 统一条目 → 去重/标签 → 聚合展示的工作流与数据模型。没有把上游 NestJS/Flutter 或 Harken 服务作为本应用的已运行后端，也没有声称复用了其整套分析功能。
- **FreshRSS**：参考保存过滤查询、HTML/RSS 分享和阅读工作流；可作为轻量展示方案。当前网站使用自己的 React 前端，不依赖 FreshRSS 账户或数据库。
- **RSS-Bridge**：参考公开社区/作者/关键词到 RSS 的转换方式，作为可选外部采集来源思路。其 Reddit `user` 模式是某用户发布的内容，不是本人订阅首页。
- **TrendRadar / NewsNow**：参考热榜/RSS 分组、来源标识、原文跳转和聚合网站展示。没有把热榜筛选当成任意全站个人时间线搜集能力。
- **OpenMagpie**：参考社会监听的数据和产品组织方式；当前没有运行其容器、企业目录或整套服务。
- **x-summary / Freed**：参考本人信息流采集、摘要和统一阅读的产品路线；没有运行它们的服务，也没有把上游摘要或捕获模块计入已完成能力。
- **AsyncPRAW**：保留为异步 Reddit 接入备选；当前声明和使用路线为 PRAW，未同时安装或切换为 AsyncPRAW。

## 账号信息流的边界

X 本人首页使用本人登录会话 Cookie，不等于指定作者公开发帖列表。RSSHub 两个首页路由调用 Web GraphQL 的 `HomeTimeline` 和 `HomeLatestTimeline`；仅配置第三方 API URL 或开发者 API Key 不代表这些首页路由能直接使用。上游 Cookie 池会轮换多个 token，因此若使用 RSSHub 获取本人首页，应将不同账号的实例/凭证配置隔离。本应用也应按本地账号会话管理数据来源，避免混合不同人的首页。

源码中存在 For You/Following 路径，只说明上游已有实现。本次下载没有使用本人真实凭证进行验证，未核实登录成功率、数据完整性、推荐结果与浏览器页面的一致性。RSS 订阅或本地网站重新排序后，展示顺序也可能与原平台首页不同。

Reddit 的关键词、作者公开帖、社区列表和登录后的订阅首页是不同读取范围；本人订阅内容需要相应授权。读取本人订阅列表可以用于建立监控来源，但不应称为完整复刻 Reddit 网站的推荐算法。

## 源码与许可证记录

参考目录保存的是未修改的上游仓库。Market Radar 没有复制、vendor 或直接导入 AGPL/GPL 上游项目源码，也不复制许可证未知的代码；PRAW、Twikit 通过依赖声明安装。其他项目仅为工作流、数据结构与界面行为参考，不将这些思路描述成已部署的服务。

表中的许可证名称按下载 commit 的根许可证文件识别，原始完整条款保留在对应仓库。这个清单提供事实记录，不作商用、分发或衍生作品的法律结论。根许可证不能替代对子目录或第三方依赖条款的逐项查看；例如 OpenMagpie README 对可选企业目录另有说明。
