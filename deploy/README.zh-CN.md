[English](README.md) · [简体中文](README.zh-CN.md)

# HTTPS 部署

Market Radar 可作为单人私有服务部署到 **https://myaistock.top/market-radar/**。一个容器、一个后端进程运行应用，数据单独持久化。Nginx 提供 HTTPS 和整站身份认证，并在转发时去掉 `/market-radar/` 前缀。

## 安装与启动

服务器需安装 Docker Compose 和 Nginx，将确认过的代码版本放到 `/opt/market-radar/app`：

```bash
sudo install -d -m 700 -o 10001 -g 10001 /opt/market-radar/data
cd /opt/market-radar/app
cp deploy/runtime.env.example deploy/runtime.env
chmod 600 deploy/runtime.env
docker compose -f deploy/compose.yaml build
docker compose -f deploy/compose.yaml up -d --no-build
docker compose -f deploy/compose.yaml ps
curl --fail http://127.0.0.1:8788/health
```

镜像按前后端锁文件安装依赖，不包含本地数据库、账号会话、环境文件或 API 密钥。运行数据写入 `/data`，临时文件写入临时目录。采集任务和数据库使用单个后端进程。

## HTTPS 路由

修改 [Nginx 示例](nginx-subpath.conf.example)，加入现有域名的 HTTPS server 配置块。`auth_basic_user_file` 使用单独管理的密码文件，或复用已有工作空间的密码文件。先备份原配置，执行 `nginx -t` 成功后再 reload，保留其他应用的原路由。

容器端口默认仅映射到 `127.0.0.1:8788`。修改端口时，同时修改 `RADAR_HOST_PORT` 和 Nginx 上游。设置、账号会话和资料库由该工作空间共享，因此服务器必须为整个应用开启认证。

`RADAR_PUBLIC_URL` 必须是准确的外部 HTTPS 地址，包含子路径。后端只信任该配置的 Host、Origin 及健康检查所需的本机访问，不依赖转发请求头推断可信域名。相同前端构建也可继续在 localhost 根路径运行。

## 账号与翻译

在 **设置 → 翻译 API** 输入自己的 API 地址、密钥和模型；也可编辑服务器私有的 `deploy/runtime.env`，修改后重启应用。默认模型为 `deepseek-flash`。界面中英文切换无需 API，原始内容翻译需要已配置的服务。

Reddit 应用的回调地址应与 **设置 → 账号** 显示的一致：

```text
https://myaistock.top/market-radar/api/connections/reddit/callback
```

先在 Reddit 应用设置中注册该地址，再授权。其他安装中的 localhost 回调需要重新配置。无图形桌面的服务器支持导入 X Cookie JSON，本地独立浏览器登录仍适用于桌面环境。服务器与本地安装各自保存数据库和加密账号设置。

## 更新、检查与恢复

先以独立 `RADAR_IMAGE` 标签构建新镜像，再替换本应用容器；保留旧镜像和配置用于回滚。通过 HTTPS 检查页面、资源、`/health`、`/api/connections` 和同源 API 请求；未认证访问应返回 `401`，其他 Origin 应返回 `403`。检查其他服务的容器 ID 和启动时间未改变。

持久化数据位于 `/opt/market-radar/data`。备份时先停止本应用，保留完整目录中的加密密钥、加密凭据及数据库 WAL 文件，不提交备份或环境文件到 Git。回滚时将 `RADAR_IMAGE` 指向旧镜像，只重建本应用服务，保留数据目录。

```bash
docker compose -f deploy/compose.yaml logs --tail 100 app
docker compose -f deploy/compose.yaml stop app
# 备份 /opt/market-radar/data 后重新启动：
docker compose -f deploy/compose.yaml start app
```
