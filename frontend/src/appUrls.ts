/** Resolve the app directory, preserving a reverse-proxy prefix and excluding SPA state. */
export function applicationBaseUrl(documentBaseURI: string, viteBase = "./"): string {
  const documentUrl = new URL(documentBaseURI);
  documentUrl.search = "";
  documentUrl.hash = "";
  // Production normally redirects to a trailing slash. Keep API calls inside the
  // app even while opening an uncanonicalized prefix such as /market-radar.
  if (!documentUrl.pathname.endsWith("/") && !documentUrl.pathname.endsWith(".html"))
    documentUrl.pathname += "/";
  const base = new URL(viteBase || "./", documentUrl);
  if (!base.pathname.endsWith("/")) base.pathname += "/";
  base.search = "";
  base.hash = "";
  return base.href;
}

export function applicationApiUrl(path: string, documentBaseURI: string, viteBase = "./"): string {
  return new URL(`api/${path.replace(/^\/+/, "")}`, applicationBaseUrl(documentBaseURI, viteBase)).href;
}
