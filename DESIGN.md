---
name: Market Radar / 交易雷达
description: 本地交易研究工作台 v0.5 的已实现视觉系统
colors:
  bg: "#f5f7fa"
  surface: "#fff"
  surface-soft: "#f7f9fc"
  ink: "#263248"
  strong: "#18273e"
  muted: "#59687e"
  subtle: "#526279"
  line: "#e6eaf0"
  line-strong: "#d5dce6"
  blue: "#2e5dde"
  blue-hover: "#244ec2"
  blue-soft: "#edf2ff"
  success: "#27845e"
  error: "#bc4948"
typography:
  headline:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif'
    fontSize: "27px"
    fontWeight: 650
    lineHeight: 1.4
    letterSpacing: "-0.035em"
  title:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif'
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.5
  reading-title:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif'
    fontSize: "23px"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif'
    fontSize: "14px"
    lineHeight: 1.6
  reading-body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif'
    fontSize: "15px"
    lineHeight: 1.85
  label:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif'
    fontSize: "12px"
    lineHeight: 1.6
rounded:
  surface: "8px"
  button: "6px"
  field: "5px"
  tag: "3px"
spacing:
  compact: "8px"
  control: "12px"
  section: "24px"
  workspace: "32px"
components:
  button-primary:
    backgroundColor: "{colors.blue}"
    textColor: "#fff"
    rounded: "{rounded.button}"
    padding: "10px 15px"
  button-primary-hover:
    backgroundColor: "{colors.blue-hover}"
    textColor: "#fff"
    rounded: "{rounded.button}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    padding: "10px 15px"
  nav-active:
    backgroundColor: "{colors.blue-soft}"
    textColor: "{colors.blue}"
    rounded: "{rounded.button}"
    padding: "9px 12px"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.surface}"
---

# Design System: Market Radar / 交易雷达

## Overview

**Creative North Star: "本地交易研究工作台"**

v0.5 保留浅灰工作区、白色面板、系统字体和蓝色交互强调，把操作结构调整为六个任务入口。真实资讯和行情占据页面主体；界面通过标题、分隔线和留白说明下一步，而不是堆叠说明卡片。

资讯页分开“从外部搜集”和“在本地筛选”。未选中资讯时列表使用全部宽度，选中后给正文足够空间。设置将账号、研究、RSS、翻译 API 和来源状态分区；行情先呈现报价、数据质量和 K 线，再通过页签查看信号、相关资讯与规则。

**Key Characteristics:**

- 六个稳定入口：News library、Following、For you、Saved、Markets & signals、Settings。
- 来源、时间、原链接和数据状态始终可辨认；缺失数据有文字解释。
- 蓝色用于可操作项、选择和焦点，状态同时使用文字。
- 英文界面默认，中文界面与资讯内容语言各自控制。

记录依据为当前 `styles.css`、后加载的 `workspace.css` / `settings.css`、行情样式和组件实现。本轮查看了 `output/playwright/v05-qa/` 内真实桌面、375px / 390px 手机、英文/中文与 light/dark 截图，包括资讯、阅读、账号、API、研究草稿及行情。最终截图确认桌面本地搜索宽度、手机 X 关闭图标与 16px 字段、默认关闭的图表信号标记。根代理另实测浏览器返回、行情 → API → 返回的选择连续性、标记切换、375px 无水平溢出与无控制台错误。真实账号登录、所有错误路径及完整无障碍验收未完成。

## Colors

前置 tokens 记录 light 模式的最终值；`workspace.css` 覆盖基础样式的工作区底色与辅助文字。白面板置于略带蓝灰的背景，正文与辅助文字采用两档深度。

### Primary

- **交互蓝（blue / blue-hover）**：采集、连接、保存等动作；链接与焦点；悬停时加深。
- **浅蓝选择面（blue-soft）**：当前导航、选中资讯和选中阅读语言。

### Neutral

- **工作区浅灰（bg）**：页面底色，衬托白色的任务区域。
- **白色操作面（surface）**：导航、采集表单、资讯列表、阅读与设置。
- **柔灰辅助面（surface-soft）**：提示、折叠说明与悬停。
- **深蓝灰文字（strong / ink）**：标题、正文与报价。
- **灰蓝辅助文字（muted / subtle）**：来源、时间、摘要和帮助文字。
- **浅分隔线（line / line-strong）**：列表行、页签与输入框轮廓。

### Status

success 与 error 配合“已配置”“未连接”“抓取失败”等文字使用。历史报价、新鲜度未确认、未收盘和数据窗口有限必须如实说明。

暗色沿用同样角色：背景 `#121923`、表面 `#18212e`、辅助面 `#1c2736`、正文 `#d1d9e7`、标题 `#ecf0f8`、辅助文字 `#a6b2c3` / `#b1bdd0`，交互蓝 `#86a5ff`，选择面 `#253753`。本轮看过手机资讯暗色截图；这不等于所有暗色页面已验收。

## Typography

**字体：** 系统 sans-serif 栈，无外部品牌字体；代码、回调地址和数值可使用原有等宽/表格数字处理。

| 用途 | 当前实现 |
| --- | --- |
| 资讯页面标题 | 桌面 27px，手机 25px；650 字重 |
| 设置/行情页面标题 | 桌面 26px / 25px，手机 23px |
| 资讯行标题 | 桌面 16px，手机 15px；1.5 行高 |
| 资讯摘要 | 13px、1.65 行高；最多两行 |
| 阅读标题 | 桌面 23px，手机 22px；1.4 行高 |
| 阅读正文 | 15px、1.85 行高，最大 75ch |
| 来源、状态与控件 | 主要 12–13px；紧凑主题标签及行情元数据 11px |
| 搜索字段 | 桌面采集 14px、本地筛选 13px；手机 16px |
| 设置字段 | 桌面 13px，手机 16px |
| 品牌文字 | 桌面 19px；中等屏幕 17px |

标题和长地址允许换行。来源正文保持原始语言，用户关键词保持原样；切换界面语言不把未知文本自动改写为中文。

## Layout

桌面左侧为任务导航，顶栏为工作区名称、界面语言和来源入口。主区域按 32px 边距对齐。默认资讯库展示所有已收录渠道；Following 与 For you 使用各自渠道条件，Saved 使用收藏条件。渠道切换清除局部主题、来源与搜索筛选，避免条件残留造成假空列表。

采集面板在列表上方，拥有自己的输入和按钮。列表工具栏单独包含本地搜索、资讯语言、计数、主题、来源及排序；筛选条件以可清除标签回显。阅读工作区未选择时为单列，选中后分成 `.85fr / 1.15fr` 的列表/阅读两列，分别至少 310px / 450px。

| 断点 | 当前布局行为 |
| --- | --- |
| 常规桌面 | 导航 232px；顶栏至少 66px；阅读区两列仅在选中时出现 |
| ≥1600px | 资讯标题区域与阅读工作区最大 1536px，居中 |
| 761–1250px | 导航 210px；水平边距 24px；阅读详情覆盖右侧，宽 `min(650px, 75vw)` |
| ≤760px | 导航变 260px 抽屉；顶栏 60px；资讯 16px 边距；详情全屏覆盖；采集输入与按钮分两行 |
| ≤720px | 设置字段与研究面板单列，设置边距 16px；标签可横向滚动 |
| ≤390px | 行情边距缩至 14px；标的刷新按钮占整行 |

覆盖式详情提供关闭、Escape、焦点约束和底层滚动锁；手机导航同时将主工作区设为 inert。以上是当前代码能力，完整键盘与辅助技术验证仍应单独执行。

设置页最大 1112px，内容最大 928px，翻译 API 面板最大 840px。研究表单桌面采用说明列与字段列；保存条带未保存状态、丢弃与本区保存。行情桌面为 250px 自选列表和图表详情；1250px / 1000px 时自选列分别为 225px / 200px，手机改为当前标的 select 与可展开的管理列表。

设置与已打开的行情工作区在离开后保持挂载，草稿、当前标的与详情页签保留。设置的返回按钮按入口显示 Back to news 或 Back to markets；隐藏行情区不参与相关资讯翻译。

## Elevation & Depth

工作区以底色和细边界分层，面板默认平面。选中资讯使用浅蓝面与 1px 内描边，不再使用粗侧边线。采集输入区移除了基础搜索阴影。

设置保存条仅使用 `0 5px 12px rgb(18 36 65 / 5%)` 的弱阴影；中等屏幕阅读覆盖使用 `-12px 0 32px #18273e22`；Toast 使用 `0 8px 30px #111a3224`。抽屉有半透明遮罩。导航和行状态延续短过渡，并保留 reduced-motion 支持。

## Shapes

面板与品牌标记主要为 8px 圆角，按钮/导航为 6px，字段为 5–6px，紧凑标签为 3–4px。细线区分列表和表单，不用装饰性光晕。来源标记是小方形底，状态圆点旁必须有可理解的文字。

## Components

### Navigation

任务导航包含六入口，Settings 在底部。My keywords 为纵向文本快捷项：点击筛选本地资讯库并填入采集输入。手机顶栏菜单包含全部入口，另提供四个资讯频道页签。URL hash 保存工作区、频道和本地筛选，支持刷新与浏览器返回。

### Collection and local filters

Search & collect 明确获取外部新内容，列出实际参与的来源。来源选择只筛选本地列表，不决定下一次采集来源。Following / For you 使用账号采集入口；没有可用账号时按钮直接进入连接设置。Saved 的刷新读取本地收藏。

本地工具栏保留主题、来源与排序；手机允许换行，不隐藏排序。资讯内容 Original / 中文 控件与顶栏中文 / English 分开。未配置 API 的中文阅读提示直接链接 Translation API；进行中、失败与缓存命中按真实返回状态显示。

### Feed rows and reading

列表按来源/作者/时间、标题、真实摘要、主题与原链接组织。收藏是独立按钮；无意义的标题重复摘录被省略。行内摘要必须区分来源摘录与 AI 摘要。

阅读详情默认展示来源文本。顶部提供收藏和关闭，覆盖式详情使用 X 关闭图标。标题后显示作者、时间和 Open original post，再提供 Overview / Source text。正文中明确采集文本可能只是摘录；完整原文仍通过源链接查看。尚未得到中文正文时保留原文并解释状态；收录渠道等 provenance 折叠在下方。

### Settings and fields

五个设置分区分别为 Accounts、Research、RSS feeds、Translation API、Source status。账号先展示登录与状态，导入已有会话等高级入口折叠。RSS 先展示自己的来源，再展开预设和 RSSHub。

Research 与 RSS 分区保存各自字段；其他分区的未保存内容保留。页面切换期间设置组件保持挂载，未保存提示提供返回相应分区的入口。API 字段展示地址、模型和密钥存在状态；已有密钥不回显，改变提供商需要新密钥。说明明确界面语言不需要 API，资讯翻译需要自己的 LLM 服务。

### Market chart and detail tabs

先显示标的、报价/币种、来源时间与质量说明，再展示价格、MA20/MA60、OHLC 与成交量。图表信号标记默认关闭，通过 Show signal markers 显示；切换不重建图表。Signals、Related news、Data & rules 分别承载事件证据、相关本地资讯和完整元数据/规则，页签支持键盘方向键。

手机 select 直接选择当前标的，Manage 展开删除/管理列表，避免自选行把图表推得过远。相关资讯拥有独立内容语言控件和 API 配置入口；跳转资讯库后应用对应关键词筛选。

### Feedback and empty states

加载、无筛选结果、未收录个人频道、收藏为空、读取失败和部分采集成功分别说明原因与下一步。来源状态进入专门设置分区，不占据默认阅读区。错误信息不使用成功图标；重试保留已有内容与草稿。界面不以模拟帖子或行情填充空状态。

## Do's and Don'ts

### Do

- **Do** 延续系统字体、浅灰工作区和白色面板，蓝色承担操作与选择。
- **Do** 清楚区分外部采集、本地筛选、界面语言和资讯语言。
- **Do** 保留正文阅读空间、原链接和数据质量说明。
- **Do** 按设置分区保存，并明确呈现未保存草稿。
- **Do** 用实际数据与可检查的规则解释行情信号。

### Don't

- **Don't** 将本地来源筛选传成个人频道的采集范围。
- **Don't** 把未翻译文本、短摘录或 AI 摘要称为完整中文原文。
- **Don't** 将历史报价展示成已验证的实时行情，或把新闻相关性描述为因果关系。
- **Don't** 将静态截图复审写成真实账号登录或完整无障碍验收。
