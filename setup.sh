#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v node >/dev/null || ! command -v npm >/dev/null; then
  echo '需要 Node.js 22.12+ 和 npm。安装后重新执行 ./setup.sh。'
  exit 1
fi
node -e 'const [major,minor]=process.versions.node.split(".").map(Number);if(major<22||(major===22&&minor<12)){console.error("需要 Node.js 22.12+");process.exit(1)}'
if ! command -v uv >/dev/null; then
  echo '需要 uv 管理 Python 依赖。可安装 uv 后重新运行，参见 README.md。'
  exit 1
fi
echo '安装 Python 3.12 环境与后端依赖…'
(cd backend && uv sync --python 3.12 --extra dev)
echo '安装前端依赖…'
npm --prefix frontend ci
echo '安装 X 登录所需的隔离浏览器…'
backend/.venv/bin/python -m playwright install chromium --no-shell
echo '构建本地网站…'
npm run build
echo '安装完成。运行 ./start.sh 或 npm start，然后访问 http://localhost:8787。'
