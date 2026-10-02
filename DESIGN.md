---
name: 交易雷达 / Market Radar
description: 本地交易资讯研究工作台的已实现视觉系统
colors:
  bg: "#f3f5f8"
  surface: "#fff"
  surface-soft: "#f7f8fa"
  ink: "#263248"
  strong: "#18273e"
  muted: "#627087"
  subtle: "#58667c"
  line: "#e6eaf0"
  line-strong: "#d5dce6"
  blue: "#2e5dde"
  blue-hover: "#244ec2"
  blue-soft: "#edf2ff"
  success: "#27845e"
  error: "#bc4948"
typography:
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", sans-serif"
    fontSize: "26px"
    fontWeight: 650
    lineHeight: 1.4
    letterSpacing: "-0.035em"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.65
    letterSpacing: "-0.012em"
  reading-title:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.7
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", sans-serif"
    fontSize: "14px"
    lineHeight: 1.6
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", \"PingFang SC\", \"Hiragino Sans GB\", \"Microsoft YaHei\", sans-serif"
    fontSize: "11px"
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
    padding: "10px 12px"
  panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.surface}"
---

# Design System: 交易雷达 / Market Radar

## Overview

**Creative North Star: "本地交易研究工作台"**

当前视觉世界是一张本地交易研究工作台：用清晰的标题、来源、时间和收录渠道帮助用户扫描资讯，选中后在阅读区核对内容与原链接。页面以浅灰工作区、白色操作面板、深蓝灰文字和少量蓝色交互强调构成，密度适中，图标用于提示操作和来源。

品牌采用已实现的“交易雷达 / Market Radar”文字和蓝色雷达标记。页面没有额外插画或装饰图像；真实标题和采集元数据是主要视觉内容。字体使用操作系统无衬线栈，同时适配中文界面和英文资讯。

**Key Characteristics:**

- 用标题、来源、时间建立阅读顺序；原文链接始终可找到。
- 将关键词资讯、我的关注、为我推荐、已收藏分成可辨认的渠道。
- 蓝色表达动作、选中和焦点；状态同时带文字。
- 列表负责扫描，阅读区负责核对，设置页负责连接和加工配置。

本文件基于 `frontend/src/styles.css`、`App.tsx`、`PRODUCT.md` 和桌面资讯/阅读/账号页、手机资讯/阅读截图整理；另查看了稳定的手机账号页。截图可见已收录资讯、收藏、来源状态和未连接账号。加载、空内容、接口错误、部分采集失败、已连接账号和暗色效果，以下仅按代码说明，没有在本轮逐一视觉验证。当前 tokens 与行为按最新代码记录：只重复标题的预览被省略，关闭的手机导航设为不可见，辅助文字加深且原 10px 元数据升为 11px，手机图标操作区为 44px。评审读取的截图包含这些小修之前的状态；本轮未另行核查修改后的最终截图。

## Colors

颜色值以前置 tokens 和现有 CSS 为准。白色面板置于浅灰背景，深蓝灰保持正文和标题层级，蓝色只承担操作强调与选中反馈。

### Primary

- **交互蓝（blue）**：搜索、连接账号等主要动作；活跃渠道、主题、收藏、链接和键盘焦点。
- **加深的交互蓝（blue-hover）**：主按钮悬停反馈。
- **浅蓝选择面（blue-soft）**：选中资讯、当前导航、辅助状态背景。

### Neutral

- **工作区浅灰（bg）**：主页面背景。
- **白色操作面（surface）**：导航、资讯列表、阅读区和连接设置面板。
- **柔灰辅助面（surface-soft）**：上下文区、说明、行悬停。
- **深蓝灰正文（ink / strong）**：正文、主标题、资讯标题。
- **灰蓝辅助文字（subtle / muted）**：摘要、来源、时间、描述和次要状态。
- **浅分隔线（line / line-strong）**：列表行与区块分隔、输入框边界。

### Status

成功状态使用 success，错误使用 error。来源和账号状态必须同时显示“可用”“未连接”“错误”等文字，不能只依赖圆点颜色。

代码另提供 `[data-theme="dark"]` 调色，沿用相同布局与组件角色。本轮没有检查暗色截图，不将它写成已完成视觉验收。

## Typography

**字体栈：** 系统 sans-serif，按平台使用 Apple/Segoe UI/苹方/微软雅黑等字形，不加载独立品牌字体。

| 用途 | 已实现层级 |
| --- | --- |
| 页面标题 | headline；桌面 26px，手机 24px |
| 资讯行标题 | title；桌面 16px，手机 15px，宽屏 17px |
| 阅读标题 | reading-title；桌面 18px，手机 21px |
| 全局正文 | body；14px、1.6 行高 |
| 行摘要 | 桌面/手机 12px、1.8 行高；最多两行 |
| 阅读正文 | 桌面 13px、1.95 行高；手机 15px |
| 元数据/标签 | 多为 11–12px；来源、作者、时间在标题前或独立信息区 |

标题允许自然换行并处理长字符串，避免英文标题挤出内容区。列表摘要限制为两行；阅读内容继续向下展开。计数使用表格数字以减少跳动。

## Layout

桌面使用固定左导航、主工作区，以及资讯列表旁的上下文/阅读区。左导航宽 224px，主工作区让出对应宽度。顶栏高至少 65px；搜索、渠道切换和阅读工作区按 32px 水平边距对齐。阅读区默认 320px，列表占剩余宽度。设置页居中，最大宽度 1120px，连接面板最大 900px。

| 断点 | 当前代码行为 |
| --- | --- |
| ≥1550px | 阅读区增至 365px，资讯行稍放宽字号和留白 |
| ≤1250px | 导航 205px，阅读区 280px，水平边距 25px，隐藏排列选择 |
| ≤1000px | 未选中资讯时隐藏上下文区；选中时保留列表 + 300px 阅读区 |
| ≤760px | 导航改抽屉；主工作区不再让出侧栏；20px 内容边距；详情变全屏覆盖；表单单列 |
| ≤390px | 渠道间距和字号收紧，资讯行隐藏作者与间隔点，来源仍保留 |

稳定的手机截图中，资讯和账号页均为单列，没有侧栏挤压正文；手机图标操作区的最终尺寸按最新 CSS 记录。手机阅读页以白色全屏内容区和粘性工具栏承载长标题、打开原文、内容切换和收录信息。抽屉覆盖页面并带遮罩，关闭后由 CSS `visibility` 隐藏；详情打开时冻结底层滚动，关闭后恢复。这里记录的是代码行为，不代表本轮逐项验证了键盘顺序或滚动恢复。

## Elevation & Depth

主体层级由底色和细边界构成。导航、列表、阅读区和设置面板大多平面呈现。选中行用浅蓝背景与左侧 3px 蓝线表达位置；悬停仅轻微换底色。搜索框具有很弱的底部阴影，焦点则用边界和浅蓝环强调。

Toast 用深色表面与扩散阴影浮在当前操作之上。手机抽屉带半透明遮罩；详情作为全屏阅读层覆盖列表。导航过渡为 200ms，资讯行换底色为 120ms。代码支持 `prefers-reduced-motion` 关闭动画和过渡。

## Shapes

容器采用轻圆角：面板/搜索区 8px，按钮/导航项 6px，字段 5px，标签 3px。细线负责分区，组件轮廓以矩形为主。来源标记是小方形图标底，状态为小圆点，品牌标记使用更明显的圆角蓝色方块。

## Components

### Navigation and channels

左侧主题导航展示主题名称和已收录计数；浅蓝当前项保持位置可见。底部固定提供“来源与账号”和主题切换。手机通过顶栏菜单打开侧栏。主渠道使用文字与线性图标，当前渠道有蓝色文字和底部蓝线；手机隐藏计数但保留渠道名称。

### Search and local filters

顶部搜索是白底、浅边框的横向字段与蓝色“跨源搜索”按钮。帮助文字区分从来源获取数据与收录后的本地筛选。列表工具栏含计数、已收录内容过滤、来源选择和排列方式；窄屏按断点压缩辅助控件。焦点采用蓝边与浅蓝环。

### Feed rows

每行按来源/作者/时间、标题、可用摘要、主题标签和原文链接组织。未读有蓝点；已读标题弱化；选中行保持浅蓝底和蓝色左边线。收藏使用独立按钮，已收藏显示填充图标。标题打开本地详情，原文链接在新标签打开来源。

最新代码在来源仅提供标题或近似重复标题时不重复显示行预览；真实不同内容和 AI 摘要继续显示。预览调整属于已读取代码，本轮截图未证明最终修改后的行高度。摘要标签区分“原文摘录”和“AI 摘要”，不能把来源摘录标成生成分析。

### Reading pane

顶栏有收藏和关闭；手机上的图标按钮、紧凑图标按钮和收藏按钮均扩为 44 × 44px 操作区。内容依次显示来源、标题、作者/时间、打开原文、整理内容/原始文本、研究主题、命中关键词及收录来源。原始文本指采集时来源返回的文本，完整文章或讨论通过原链接查看。没有完整文本时显示来源仅提供标题或简短文本的说明。代码支持 Escape 关闭和按条件显示 AI 摘要动作；本轮只查看静态阅读效果。

### Account panels and fields

X、Reddit 各有独立面板、平台标记、能力描述、连接状态和操作区。X 提供独立浏览器登录和折叠的已有会话入口；Reddit 提供应用信息字段、OAuth 连接与回调地址。说明文字就近跟随操作，未连接状态明确。桌面字段两列，手机单列；手机表单字段字体 16px。关键词/加工、RSS 来源通过设置标签页进入。

### Feedback, empty and error states

| 状态 | 代码中的表现 | 本轮证据 |
| --- | --- | --- |
| 已收录真实内容 | 展示后端返回条目、原链接和来源信息；数量使用实际结果 | 资讯截图可见 |
| 账号未连接 | 平台面板显示未连接与登录/授权入口 | 账号截图可见 |
| 正在读取 | 四条灰色骨架行，附“正在读取资讯”标签 | 代码已检查，未截图验收 |
| 无筛选结果 | “没有符合筛选条件的内容”，提供调整与清除筛选 | 代码已检查，未截图验收 |
| 首次无内容 | “开始收集你的交易信息”，引导搜索最新信息 | 代码已检查，未截图验收 |
| 关注/推荐未收录 | 分别说明连接账号后拉取关注内容或 X 推荐流/Reddit API 首页 | 代码已检查，未截图验收 |
| 收藏为空 | 提示点击资讯收藏按钮，继续阅读 | 代码已检查，未截图验收 |
| API 读取错误 | “暂时无法读取资讯”、返回错误说明与重试动作 | 代码已检查，未截图验收 |
| 采集进行/结束/失败 | 来源级状态、数量及可展开错误；保留部分成功结果说明 | 代码已检查，未截图验收 |
| 短反馈 | 深色 Toast，6 秒后关闭并可手动收起，`role="status"` | 保存与连接提示截图可见；计时未实测 |

来源未连接、未授权、限流或采集失败时应保持真实状态；空列表用操作指引承接，不添加模拟帖子或市场报价填充。

## Do's and Don'ts

### Do

- **Do** 延续系统字体、浅灰工作区、白色面板和蓝色交互强调。
- **Do** 保持来源、发布时间、收录渠道和原文入口可辨认。
- **Do** 用文字配合颜色说明连接、加载与失败状态。
- **Do** 继续将“已抓取的数据”与“尚未连接的来源”分开呈现。
- **Do** 在增加页面时沿用列表扫描、详情核对、设置连接的操作结构。

### Don't

- **Don't** 用虚构帖子、数值或成功提示代替缺失的真实结果。
- **Don't** 把摘录、原始文本和 AI 摘要的名称互相替代。
- **Don't** 将账号首页读取描述为完整复制平台推荐算法。
- **Don't** 把本轮未查看的错误、暗色或已连接状态写成已完成视觉验收。

## 中文阅读扩展（2026-10-02）

顶栏增加「一键切换中文／切回原文」文字按钮，沿用蓝色动作与轻边框，手机触控高度44px。搜索区显示DeepSeek Flash翻译进度和错误重试；资讯行用中文译文／待译／失败标签区分状态。中文模式翻译标题、摘要和来源正文，详情提供「中文全文」及折叠的原始文本入口。原文、作者和链接独立保留；模式记忆、分页追加和缓存均由实际后端处理。
