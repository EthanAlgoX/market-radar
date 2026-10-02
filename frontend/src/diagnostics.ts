/** Local application diagnostics only. Never use this on article text or editable user content. */
const DIAGNOSTICS: [string, string][] = [
  ["财经 RSS", "Financial RSS"],
  ["RSS 地址必须是无登录凭据的 HTTP / HTTPS URL", "RSS URL must be an HTTP / HTTPS URL without login credentials"],
  ["模型 API 地址必须是无登录凭据的 HTTP / HTTPS URL", "Model API URL must be an HTTP / HTTPS URL without login credentials"],
  ["RSSHub 地址必须是无登录凭据的 HTTP / HTTPS URL", "RSSHub URL must be an HTTP / HTTPS URL without login credentials"],
  ["回调必须为本机 8787 端口的 /api/connections/reddit/callback", "The redirect must use localhost port 8787 and /api/connections/reddit/callback"],
  ["X 连接状态检查失败", "X connection status could not be checked"],
  ["已配置公开来源；尚未采集", "Public sources are configured; no collection has run yet"],
  ["使用已配置 RSSHub；本人 X 会话未连接", "Using the configured RSSHub instance; your X account is not connected"],
  ["Reddit 连接验证失败", "Reddit connection verification failed"],
  ["关键词搜索需要填写查询内容", "Enter a query for keyword search"],
  ["等待采集", "Waiting for collection"],
  ["采集任务未完成，已保存的内容仍可查看", "Collection did not complete; saved content remains available"],
  ["RSSHub 服务端 X 会话尚未核验为本人，来源身份请在 RSSHub 侧确认", "The RSSHub server's X session has not been verified as yours. Confirm account identity on the RSSHub instance"],
  ["正在请求来源", "Requesting source data"],
  ["正在重试来源", "Retrying source request"],
  ["本次窗口没有匹配内容", "No matching content in this collection window"],
  ["进程停止，重启后继续", "The process stopped; collection resumes after restart"],
  ["无效的本机 Host", "Invalid local Host"],
  ["服务仅接受本机 Host", "The service accepts local Host values only"],
  ["该网页来源未被授权访问本机服务", "This web origin is not authorized to access the local service"],
  ["已阻止外部网站访问本机服务", "Access to the local service from an external website was blocked"],
  ["翻译任务不存在", "Translation job not found"],
  ["内容不存在", "Content not found"],
  ["采集任务不存在", "Collection job not found"],
  ["此来源尚未接入讨论正文，请打开原帖查看", "Discussion text is not supported for this source. Open the original post"],
  ["使用最近 10 分钟的讨论缓存", "Using the discussion cache from the last 10 minutes"],
  ["此操作仅支持资讯文章；社区帖子请打开外链文章查看", "This action supports news articles only. Open a community post's linked article"],
  ["关注作者列表过长", "The followed-author list is too long"],
  ["llm.enabled 需要布尔值", "llm.enabled must be a boolean"],
  ["模型名称和 API 地址需要字符串", "Model name and API URL must be strings"],
  ["Reddit 授权状态无效或已过期", "Reddit authorization state is invalid or expired"],
  ["Reddit 授权缺少 code 或 state", "Reddit authorization is missing code or state"],
  ["请在设置中显式启用 AI 摘要并配置模型", "Enable AI summaries and configure a model in Settings"],
  ["站点图标不存在", "Site icon not found"],
  ["API 不存在", "API not found"],
  ["进程重启，等待继续采集", "The process restarted; waiting to resume collection"],
  ["旧版采集进程中断，请重新运行", "The previous collection process was interrupted. Run collection again"],
  ["翻译进程中断，已完成译文仍在本机缓存", "The translation process was interrupted. Completed translations remain cached locally"],
  ["来源已更新，请重新读取公开正文；新内容已保留", "The source changed. Reload the public article text; the new content is retained"],
  ["采集队列已满，请等待当前任务完成", "The collection queue is full. Wait for the current jobs to finish"],
  ["来源返回的内容不是有效 RSS / Atom", "The source did not return valid RSS / Atom"],
  ["该公开来源没有本人个性化推荐流", "This public source does not provide your personalized account feed"],
  ["Google News 在此接入仅提供关键词搜索", "This Google News integration supports keyword search only"],
  ["Hacker News 在此接入仅提供关键词搜索", "This Hacker News integration supports keyword search only"],
  ["Hacker News 本轮最多检索6个词组，剩余词组尚未查询", "This Hacker News run searches up to 6 phrases. Remaining phrases have not been queried"],
  ["请先在设置中启用 RSS 订阅", "Enable an RSS subscription in Settings first"],
  ["Cookie JSON 过大，请仅提供 X 会话 Cookie。", "The cookie JSON is too large. Provide only X session cookies."],
  ["请提供有效的 Cookie JSON（对象或浏览器导出的列表）。", "Provide valid cookie JSON as an object or a browser-exported list."],
  ["Cookie 列表中的每一项都需要 name 和 value。", "Each cookie-list entry must contain name and value."],
  ["Cookie JSON 必须是对象或列表。", "Cookie JSON must be an object or list."],
  ["Cookie 中必须包含非空的 auth_token 和 ct0。", "Cookies must include non-empty auth_token and ct0 values."],
  ["Cookie 值不能包含换行符。", "Cookie values must not contain line breaks."],
  ["X 帖子缺少有效发布时间，未将采集时间充当发布时间。", "The X post has no valid publication time. Collection time was not used as publication time."],
  ["X 返回了没有帖子 ID 的数据，未保存该条目。", "X returned data without a post ID. The item was not saved."],
  ["尚未连接 X 账号。", "Your X account is not connected."],
  ["X 连接操作已取消，请重新发起。", "The X connection operation was cancelled. Start it again."],
  ["X 采集依赖尚未安装，请先完成后端依赖安装。", "X collection dependencies are not installed. Install the backend dependencies first."],
  ["X 未返回有效账号身份，会话尚未确认可用。", "X did not return a valid account identity. The session has not been verified."],
  ["请先连接自己的 X 账号。", "Connect your own X account first."],
  ["正在打开独立浏览器窗口，请在该窗口登录自己的 X 账号。", "Opening a separate browser window. Sign in to your X account there."],
  ["正在验证 X 会话。", "Verifying the X session."],
  ["请在独立浏览器中完成 X 登录；完成后将自动验证并关闭窗口。", "Complete X sign-in in the separate browser. The session will be verified and the window closed automatically."],
  ["X 登录等待已超时，窗口已关闭。请重新连接或手动导入会话 Cookie。", "X sign-in timed out and the window was closed. Reconnect or import your session cookies."],
  ["浏览器登录依赖尚未安装，请安装 Playwright 或手动导入会话 Cookie。", "Browser sign-in dependencies are not installed. Install Playwright or import your session cookies."],
  ["X 登录窗口无法继续，可能被关闭、浏览器未安装或 X 拒绝自动化登录。请重试或手动导入会话 Cookie。", "The X sign-in window could not continue. It may have been closed, the browser may be missing, or X may have rejected automated sign-in. Retry or import session cookies."],
  ["已断开 X 账号并清除本地会话。", "X disconnected and the local session was removed."],
  ["X 作者查询未返回有效 ID。", "The X author lookup did not return a valid ID."],
  ["不支持的 X 采集频道。", "Unsupported X collection channel."],
  ["X 关键词采集需要提供搜索词。", "Enter a search query for X keyword collection."],
  ["X 作者需填写有效用户名，例如 naval。", "Enter a valid X username, such as naval."],
  ["X 作者帖子端点仍处于 429 冷却期，请稍后再试。", "The X author-post endpoint is still cooling down after HTTP 429. Retry later."],
  ["该 Reddit 操作已取消，未继续读取或保存结果", "The Reddit operation was cancelled. No further results were read or saved"],
  ["Reddit 单轮时间预算已用完，保留已取得的内容", "The Reddit run reached its time budget. Collected content is retained"],
  ["Reddit 单轮请求预算已用完，保留已取得的内容", "The Reddit run reached its request budget. Collected content is retained"],
  ["会话已保存，等待真实账号验证", "Session saved; waiting for account verification"],
  ["使用 Reddit OAuth 授权本人账号", "Authorize your account with Reddit OAuth"],
  ["请先配置 Reddit OAuth 应用", "Configure a Reddit OAuth app first"],
  ["请先连接本人 Reddit 账号", "Connect your own Reddit account first"],
  ["Reddit 未返回有效本人账号，会话尚未验证", "Reddit did not return a valid account identity. The session has not been verified"],
  ["Reddit 授权状态无效或已过期，请重新发起连接", "Reddit authorization state is invalid or expired. Start the connection again"],
  ["Reddit 未返回长期授权，会话未保存", "Reddit did not grant long-term authorization. The session was not saved"],
  ["Reddit 未返回有效本人账号", "Reddit did not return a valid account identity"],
  ["已断开 Reddit 账号", "Reddit disconnected"],
  ["不支持的 Reddit 采集频道", "Unsupported Reddit collection channel"],
  ["Reddit 关键词采集需要搜索词", "Enter a query for Reddit keyword collection"],
  ["Reddit 用户名或社区名无效", "Invalid Reddit username or community name"],
  ["该 Reddit 操作已取消，未交付旧账号结果", "The Reddit operation was cancelled. Results from the previous account were not delivered"],
  ["本轮按帖子和来源预算截断；未扫描的来源将在后续轮转采集", "This run was limited by post and source budgets. Unscanned sources will be collected in later rotations"],
  ["Reddit 投稿 ID 无效", "Invalid Reddit submission ID"],
  ["本地进程重启，等待恢复", "The local process restarted; waiting to resume"],
  ["自选列表最多 20 个标的，请先移除一个", "The watchlist supports up to 20 instruments. Remove one first"],
  ["已添加；点击刷新后采集", "Added to your watchlist. Click refresh to fetch market data"],
  ["拒绝重复时间戳，未覆盖原有行情", "Duplicate timestamps were rejected. Existing market data was not overwritten"],
  ["拒绝将不同来源或口径拼入同一行情序列", "Data with a different source or convention cannot be merged into this market series"],
  ["历史来源已修订，但窗口不足以重新确认该旧信号", "The source revised its history, but this window is too short to revalidate the old signal"],
  ["来源修订或质量变化后不再确认", "No longer confirmed after source revisions or quality changes"],
  ["尚未采集行情", "Market data has not been collected yet"],
  ["请先添加自选标的", "Add a watchlist instrument first"],
  ["行情任务队列已满，请等待现有任务完成", "The market refresh queue is full. Wait for existing jobs to finish"],
  ["自选标的不存在或已删除", "The watchlist instrument does not exist or was removed"],
  ["加密资产请输入 BTC/USDT 一类 Binance 现货 USDT 交易对", "For crypto, enter a Binance spot USDT pair such as BTC/USDT"],
  ["美股请输入 AAPL 一类股票或 ETF 代码", "For US equities, enter a stock or ETF symbol such as AAPL"],
  ["港股请输入 0700.HK 一类股票代码", "For Hong Kong equities, enter a stock symbol such as 0700.HK"],
  ["首版 A 股仅支持沪深股票六位代码，如 600519 或 000001", "China A-shares currently support six-digit Shanghai/Shenzhen stock codes such as 600519 or 000001"],
  ["A 股代码与交易所后缀不一致", "The China A-share code does not match its exchange suffix"],
  ["不支持的市场", "Unsupported market"],
  ["Yahoo 行情身份信息缺失，无法确认资产类型、币种和交易时区，未保存数据", "Yahoo metadata is missing. Asset type, currency and market timezone could not be verified; data was not saved"],
  ["Yahoo 返回的资产类型不是股票或 ETF，未保存所选股票市场的数据", "Yahoo returned an asset type other than stock or ETF. Data was not saved for the selected market"],
  ["Yahoo 行情币种或交易时区与所选市场不一致，未保存数据", "Yahoo currency or timezone differs from the selected market. Data was not saved"],
  ["来源返回重复交易日，未覆盖已有数据", "The source returned duplicate trading dates. Existing data was not overwritten"],
  ["Binance 返回重复时间戳，未覆盖已有数据", "Binance returned duplicate timestamps. Existing data was not overwritten"],
  ["Binance 返回了不完整 K 线结构", "Binance returned an incomplete candle structure"],
  ["Binance 未返回该现货交易对的行情", "Binance did not return market data for this spot pair"],
  ["行情响应超过有限窗口大小", "The market data response exceeded the bounded window size"],
  ["行情 SDK 未返回有效结果，请检查依赖与网络", "The market data SDK returned no valid result. Check dependencies and network access"],
  ["来源返回空行情；可能是代码不可用、限流或无可用交易数据", "The source returned no market data. The symbol may be unavailable, rate limited or have no trading data"],
  ["行情来源不可用", "The market data source is unavailable"],
  ["行情 SDK 未完成请求，请检查公开数据可用性、网络或限流", "The market data SDK request did not complete. Check public data availability, network access or rate limits"],
  ["来源请求超时，可稍后重试", "The source request timed out. Retry later"],
  ["无法连接来源，请检查网络或代理配置", "Unable to connect to the source. Check network or proxy settings"],
  ["仅支持不含登录凭据的 HTTP / HTTPS 地址", "Only HTTP / HTTPS URLs without login credentials are supported"],
  ["无法解析来源地址", "Unable to resolve the source URL"],
  ["来源地址指向私有、保留或元数据网络，已阻止请求", "The source URL points to a private, reserved or metadata network. The request was blocked"],
  ["来源地址无效或无法解析", "The source URL is invalid or could not be resolved"],
  ["来源地址超出可信 RSSHub 配置范围", "The source URL is outside the trusted RSSHub configuration"],
  ["RSSHub 跳转超出可信地址范围", "The RSSHub redirect is outside the trusted URL range"],
  ["来源返回了无目标的跳转", "The source returned a redirect without a destination"],
  ["该 API 不允许自动跳转，请填写最终地址", "This API does not allow automatic redirects. Enter the final URL"],
  ["来源响应超过大小上限", "The source response exceeded the size limit"],
  ["来源重定向次数过多", "The source returned too many redirects"],
  ["来源请求未完成", "The source request did not complete"],
];

const chineseToEnglish = new Map(DIAGNOSTICS);
const englishToChinese = new Map(DIAGNOSTICS.map(([zh, en]) => [en, zh]));
const OPERATIONS: [string, string][] = [
  ["验证 X 会话", "Verify X session"], ["重新验证 X 会话", "Reverify X session"],
  ["查询 X 作者", "Look up X author"], ["搜索 X 帖子", "Search X posts"],
  ["采集 X 推荐流", "Collect X For You"], ["采集 X 关注流", "Collect X Following"],
  ["读取 X 关注列表", "Read X following list"],
];
function operationLabel(value: string, locale: "en" | "zh"): string | undefined {
  const pair = OPERATIONS.find(([zh, en]) => locale === "en" ? zh === value : en === value);
  if (pair) return pair[locale === "en" ? 1 : 0];
  const author = value.match(locale === "en" ? /^采集 X 作者 @([A-Za-z0-9_]{1,15}) 帖子$/ : /^Collect posts from X author @([A-Za-z0-9_]{1,15})$/);
  return author ? locale === "en" ? `Collect posts from X author @${author[1]}` : `采集 X 作者 @${author[1]} 帖子` : undefined;
}

const PREFIX_LABELS: [string, string][] = [
  ["Reddit 搜索", "Reddit search"], ["Reddit 关注首页", "Reddit followed homepage"],
  ["Reddit 订阅社区", "Reddit subscribed communities"],
];
function diagnosticPrefix(value: string, locale: "en" | "zh"): string {
  const pair = PREFIX_LABELS.find(([zh, en]) => locale === "en" ? zh === value : en === value);
  return pair ? pair[locale === "en" ? 1 : 0] : value;
}

type Pattern = { zh: RegExp; en: RegExp; english: (...values: string[]) => string | undefined; chinese: (...values: string[]) => string | undefined };
const PATTERNS: Pattern[] = [
  { zh: /^来源暂时不可用，(\d+) 秒后重试$/, en: /^The source is temporarily unavailable\. Retrying in (\d+) seconds$/,
    english: seconds => `The source is temporarily unavailable. Retrying in ${seconds} seconds`, chinese: seconds => `来源暂时不可用，${seconds} 秒后重试` },
  { zh: /^收到 (\d+) 条 · 新增 (\d+) · 更新 (\d+) · 重复 (\d+)(?: · (.+))?$/, en: /^Received (\d+) · Added (\d+) · Updated (\d+) · Duplicates (\d+)(?: · (.+))?$/,
    english: (received, added, updated, duplicate, suffix) => `Received ${received} · Added ${added} · Updated ${updated} · Duplicates ${duplicate}${suffix ? ` · ${localizeDiagnostic(suffix, "en") ?? suffix}` : ""}`,
    chinese: (received, added, updated, duplicate, suffix) => `收到 ${received} 条 · 新增 ${added} · 更新 ${updated} · 重复 ${duplicate}${suffix ? ` · ${localizeDiagnostic(suffix, "zh") ?? suffix}` : ""}` },
  { zh: /^已验证 @([A-Za-z0-9_]{1,15}) 的 X 会话。$/, en: /^X session verified for @([A-Za-z0-9_]{1,15})\.$/,
    english: handle => `X session verified for @${handle}.`, chinese: handle => `已验证 @${handle} 的 X 会话。` },
  { zh: /^已验证 u\/([A-Za-z0-9_-]{1,40}) 的 Reddit OAuth 会话$/, en: /^Reddit OAuth session verified for u\/([A-Za-z0-9_-]{1,40})$/,
    english: username => `Reddit OAuth session verified for u/${username}`, chinese: username => `已验证 u/${username} 的 Reddit OAuth 会话` },
  { zh: /^已采集 (\d+) 条 X 信息。(存在部分失败或采样截断，详情见采集警告。)?$/, en: /^Collected (\d+) X posts\.( Some requests failed or sampling was truncated\. See collection warnings\.)?$/,
    english: (count, warning) => `Collected ${count} X posts.${warning ? " Some requests failed or sampling was truncated. See collection warnings." : ""}`,
    chinese: (count, warning) => `已采集 ${count} 条 X 信息。${warning ? "存在部分失败或采样截断，详情见采集警告。" : ""}` },
  { zh: /^已读取 (\d+) 个 X 关注账号。$/, en: /^Read (\d+) followed X accounts\.$/,
    english: count => `Read ${count} followed X accounts.`, chinese: count => `已读取 ${count} 个 X 关注账号。` },
  { zh: /^已取得 (\d+) 条 Reddit 内容(，本轮覆盖已截断)?$/, en: /^Retrieved (\d+) Reddit posts(; coverage was truncated for this run)?$/,
    english: (count, truncated) => `Retrieved ${count} Reddit posts${truncated ? "; coverage was truncated for this run" : ""}`,
    chinese: (count, truncated) => `已取得 ${count} 条 Reddit 内容${truncated ? "，本轮覆盖已截断" : ""}` },
  { zh: /^已加载 (\d+) 条讨论；完整讨论请查看原帖$/, en: /^Loaded (\d+) comments\. Open the original post for the full discussion$/,
    english: count => `Loaded ${count} comments. Open the original post for the full discussion`, chinese: count => `已加载 ${count} 条讨论；完整讨论请查看原帖` },
  { zh: /^本轮仅处理 (\d+)\/(\d+) 个指定作者，其余将在后续采集轮转。$/, en: /^This run processed (\d+)\/(\d+) selected authors\. The rest will be collected in later rotations\.$/,
    english: (count, total) => `This run processed ${count}/${total} selected authors. The rest will be collected in later rotations.`, chinese: (count, total) => `本轮仅处理 ${count}/${total} 个指定作者，其余将在后续采集轮转。` },
  { zh: /^来源返回 HTTP (\d{3})，请检查连接、权限或访问频率$/, en: /^The source returned HTTP (\d{3})\. Check connection, permissions or request frequency$/,
    english: code => `The source returned HTTP ${code}. Check connection, permissions or request frequency`, chinese: code => `来源返回 HTTP ${code}，请检查连接、权限或访问频率` },
  { zh: /^(来源|X|Reddit|RSS|RSSHub|Hacker News|讨论正文|公开正文|AI 摘要)采集未完成，请检查配置后重试$/, en: /^(Source|X|Reddit|RSS|RSSHub|Hacker News|Discussion text|Public article text|AI summary) collection did not complete\. Check configuration and retry$/,
    english: source => `${({ "来源": "Source", "讨论正文": "Discussion text", "公开正文": "Public article text", "AI 摘要": "AI summary" } as Record<string, string>)[source] ?? source} collection did not complete. Check configuration and retry`,
    chinese: source => `${({ "Source": "来源", "Discussion text": "讨论正文", "Public article text": "公开正文", "AI summary": "AI 摘要" } as Record<string, string>)[source] ?? source}采集未完成，请检查配置后重试` },
];

// Exact operation suffixes are known collector messages, not arbitrary exception text.
const X_SUFFIXES: [string, string][] = [
  ["失败：X 请求过于频繁（429），请稍后再试。", " failed: X rate limited the request (HTTP 429). Retry later."],
  ["失败：X 会话已失效或账号需要验证，请重新登录。", " failed: the X session expired or the account needs verification. Sign in again."],
  ["失败：X 拒绝访问（403），请在 X 检查登录或安全验证。", " failed: X denied access (HTTP 403). Check sign-in or security verification on X."],
  ["超时，请检查网络或代理后重试；会话尚未确认可用。", " timed out. Check network or proxy settings and retry; the session is not verified."],
  ["失败：无法连接 X，请检查本机网络或代理。", " failed: unable to connect to X. Check this computer's network or proxy."],
  ["失败：目标不可用，或 X 接口已经变更。", " failed: the target is unavailable or the X interface has changed."],
  ["失败：X 接口返回异常，可能需要重新登录或更新采集器。", " failed: the X interface returned an unexpected result. Sign in again or update the collector."],
  ["达到本次数量上限，仅保存有限采样。", " reached this run's item limit. Only a bounded sample was saved."],
  ["分页已停止（空页、重复游标或页数上限），结果可能不完整。", " pagination stopped due to an empty page, repeated cursor or page limit. Results may be incomplete."],
  ["有下一页游标但无法翻页，结果可能不完整。", " has a next-page cursor but cannot continue. Results may be incomplete."],
];

/** Return undefined for unknown diagnostics so callers retain the original diagnostic details. */
export function localizeDiagnostic(message: string, locale: "en" | "zh"): string | undefined {
  const exact = (locale === "en" ? chineseToEnglish : englishToChinese).get(message);
  if (exact !== undefined) return exact;
  for (const pattern of PATTERNS) {
    const match = message.match(locale === "en" ? pattern.zh : pattern.en);
    if (match) return (locale === "en" ? pattern.english : pattern.chinese)(...match.slice(1));
  }
  for (const [zh, en] of X_SUFFIXES) {
    const suffix = locale === "en" ? zh : en;
    if (!message.endsWith(suffix)) continue;
    const operation = operationLabel(message.slice(0, -suffix.length), locale);
    if (operation) return `${operation}${locale === "en" ? en : zh}`;
  }
  const cooldown = message.match(locale === "en" ? /^(.+)暂缓：X 端点处于 429 冷却期，请约 (\d+) 秒后再试。$/ : /^(.+) deferred: the X endpoint is cooling down after HTTP 429\. Retry in about (\d+) seconds\.$/);
  if (cooldown) {
    const operation = operationLabel(cooldown[1], locale);
    if (operation) return locale === "en" ? `${operation} deferred: the X endpoint is cooling down after HTTP 429. Retry in about ${cooldown[2]} seconds.` : `${operation}暂缓：X 端点处于 429 冷却期，请约 ${cooldown[2]} 秒后再试。`;
  }
  const laterPage = message.match(locale === "en" ? /^(.+)后续页未完成：(.+)$/ : /^(.+) later pages did not complete: (.+)$/);
  if (laterPage) {
    const operation = operationLabel(laterPage[1], locale);
    if (operation) return `${operation}${locale === "en" ? " later pages did not complete: " : "后续页未完成："}${localizeDiagnostic(laterPage[2], locale) ?? laterPage[2]}`;
  }
  const authorSupplement = message.match(locale === "en" ? /^作者 @([A-Za-z0-9_]{1,15}) 补充未完成：(.+)$/ : /^Additional posts from @([A-Za-z0-9_]{1,15}) did not complete: (.+)$/);
  if (authorSupplement) return `${locale === "en" ? `Additional posts from @${authorSupplement[1]} did not complete: ` : `作者 @${authorSupplement[1]} 补充未完成：`}${localizeDiagnostic(authorSupplement[2], locale) ?? authorSupplement[2]}`;
  const saved = message.match(locale === "en" ? /^会话已保存，但尚未验证：(.+)$/ : /^Session saved but not verified: (.+)$/);
  if (saved) return `${locale === "en" ? "Session saved but not verified: " : "会话已保存，但尚未验证："}${localizeDiagnostic(saved[1], locale) ?? saved[1]}`;
  // Only a known error suffix is localized; any source or username prefix stays byte-for-byte intact.
  const prefixed = message.match(/^(.{1,160}): (.+)$/);
  if (prefixed) {
    const detail = localizeDiagnostic(prefixed[2], locale);
    if (detail !== undefined) return `${diagnosticPrefix(prefixed[1], locale)}: ${detail}`;
  }
  return undefined;
}
