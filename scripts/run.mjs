import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const production = process.argv.includes('--production');
const environmentFile = path.join(root, '.env');
if (existsSync(environmentFile)) {
  try { process.loadEnvFile(environmentFile); }
  catch { console.error('项目 .env 配置无效，请检查格式后重新启动。'); process.exit(1); }
}
const python = path.join(root, 'backend', '.venv', 'bin', 'python');
if (!existsSync(python) || !existsSync(path.join(root, 'frontend', 'node_modules'))) {
  console.error('请先在项目目录执行 ./setup.sh，安装本地运行依赖。');
  process.exit(1);
}
const children = new Set();
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill('SIGTERM');
  setTimeout(() => { for (const child of children) child.kill('SIGKILL'); process.exit(code); }, 1500).unref();
  if (!children.size) process.exit(code);
}
process.on('SIGINT', () => stop());
process.on('SIGTERM', () => stop());
function launch(command, args, cwd) {
  const child = spawn(command, args, { cwd, stdio: 'inherit', env: process.env });
  children.add(child);
  child.on('error', error => { console.error(`无法启动本地服务：${error.message}`); stop(1); });
  child.on('exit', code => {
    children.delete(child);
    if (!stopping) stop(code || 1);
    else if (!children.size) process.exit(code || 0);
  });
  return child;
}
if (production) {
  const built = await new Promise(resolve => {
    const build = spawn('npm', ['run', 'build'], { cwd: path.join(root, 'frontend'), stdio: 'inherit' });
    build.on('error', () => resolve(false));
    build.on('exit', code => resolve(code === 0));
  });
  if (!built) process.exit(1);
}
try {
  await fetch('http://127.0.0.1:8787/health', { signal: AbortSignal.timeout(700) });
  console.error('8787 端口已有服务运行。请关闭原服务后再启动，或直接访问 http://localhost:8787。');
  process.exit(1);
} catch {}
launch(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8787', '--no-access-log', ...(production ? [] : ['--reload'])], path.join(root, 'backend'));
let ready = false;
for (let attempt = 0; attempt < 40 && !stopping; attempt++) {
  try {
    const response = await fetch('http://127.0.0.1:8787/health', { signal: AbortSignal.timeout(800) });
    if (response.ok) { ready = true; break; }
  } catch {}
  await new Promise(resolve => setTimeout(resolve, 300));
}
if (!ready) { console.error('后端未能启动，请查看上方错误。'); stop(1); }
else if (production) console.log('\n交易雷达已启动：http://localhost:8787\n按 Ctrl+C 停止服务。\n');
else {
  launch('npm', ['run', 'dev'], path.join(root, 'frontend'));
  console.log('\n开发地址：http://localhost:5173\n按 Ctrl+C 停止前后端服务。\n');
}
