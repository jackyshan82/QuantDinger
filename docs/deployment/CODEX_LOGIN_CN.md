# 本机 Codex 登录额度接入

[English](CODEX_LOGIN.md)

此可选功能通过官方 Codex CLI 和 ChatGPT 登录，在可信的本机部署中使用 Codex
账户额度，不使用 OpenAI Platform API 密钥。不要公开桥接服务、向不可信租户开放
该账户，或把登录文件放进仓库。[官方非交互文档](https://learn.chatgpt.com/docs/non-interactive-mode)。

## 配置

1. 在 Docker 主机安装独立的 **Linux** Codex CLI。已验证版本为 0.164.0，须支持
   `--ignore-user-config`、`--ignore-rules` 和 `--ephemeral`。使用
   `readlink -f $(command -v codex)` 找到实际可执行文件。
2. 运行 `docker compose build backend` 构建包含新供应商的后端。如需复用相同版本
   官方镜像中已安装的依赖，可改用
   `docker build -f backend_api_python/Dockerfile.local -t quantdinger-backend:local backend_api_python`。
   此方式同时复制应用代码、运行脚本和数据库迁移文件。更新源码后，先运行
   `docker compose run --rm --no-deps -e SKIP_AUTO_MIGRATE=false migration`
   应用尚未执行的迁移，再重建应用容器。
3. 在已忽略的根目录 `.env` 配置：

   ```dotenv
   LLM_PROVIDER=codex
   CODEX_BRIDGE_URL=http://codex-bridge:8765
   CODEX_BRIDGE_TOKEN=<至少32字符的随机内部密钥>
   CODEX_CLI_BINARY=<Linux原生Codex可执行文件的绝对路径>
   CODEX_MODEL=
   CODEX_TIMEOUT=180
   ```

   模型留空即使用 CLI 默认模型，无须填写 API Key。内部桥接密钥不能使用 ChatGPT
   的访问令牌代替。
4. 初始化私有登录数据卷并登录：

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.codex.yml run --rm \
     --user 0 --cap-add CHOWN --entrypoint sh codex-bridge \
     -c 'mkdir -p /home/quantdinger/.codex && chown 10001:10001 /home/quantdinger/.codex'
   docker compose -f docker-compose.yml -f docker-compose.codex.yml run --rm \
     --entrypoint /usr/local/bin/codex codex-bridge login --device-auth
   ```

   按官方流程在浏览器完成登录。数据卷会保存刷新后的登录状态；不要打印、提交或
   分享其中的 `auth.json`。
5. 启动桥接并重建应用容器：

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.codex.yml up -d \
     --no-deps --pull never codex-bridge backend celery-worker celery-beat
   ```

刷新“系统设置 → AI/LLM”页面即可看到 **Codex** 供应商。下拉框只选择供应商，
不会安装 CLI 或执行登录；须先配置桥接服务。

## 整套本地服务一起启动

完成配置后，在仓库根目录执行：

```bash
./scripts/local-stack.sh up
./scripts/local-stack.sh check
./scripts/local-stack.sh status
```

这是同一个 Compose 项目，由 `docker-compose.yml` 与
`docker-compose.codex.yml` 两份配置组合管理。启动入口明确包含 PostgreSQL、
缓存 Redis、持久化任务 Redis、Kafka、Codex bridge、后端、Celery worker/beat、
交易 worker、策略分发/执行 worker、Kafka 审计、调度 worker、前端和移动端，
共十五项常驻服务。回测等有限任务由 Celery worker 消费 `jobs`、`ai`、
`maintenance` 队列。数据库迁移、env-sync、kafka-init 作为 Compose 依赖执行，
成功退出属于正常状态。运行 worker 会恢复已标记为运行中的策略，启动前需核对
保存的券商账户使用模拟还是实盘。策略的 `execution_mode=live` 表示连接券商
执行；Alpaca 凭据配置 `paper=true` 时连接的是模拟账户。

`up` 等待服务就绪，并检查带鉴权的 Codex 健康接口和 Celery 队列响应。它通过
`--no-recreate`、`--no-build` 复用现有容器和镜像，仅通过 `--pull missing` 拉取
缺失镜像，适合重启恢复；
更新源码或镜像仍需按升级流程执行。桥接健康检查验证登录配置，不生成模型回答，
也不证明账户仍有剩余额度。

常驻容器均配置 `restart: unless-stopped`。本机 WSL 的 Docker 系统服务已启用，
WSL 和 Docker 启动后会自动恢复现有容器。若主动运行过
`./scripts/local-stack.sh stop`，再次执行 `up` 即可启动。WSL 重启会中断正在
运行的任务，重试前应核对数据库中的任务状态。

容器入口会将 `.env` 收紧为后端 UID 10001 所有、权限 `0600`，迁移时也会执行。
WSL 中脚本通过该发行版的 root 管理入口运行 Compose，解决主机读取权限问题。
其他 Linux 主机若当前用户无法读取，可执行 `sudo ./scripts/local-stack.sh up`。
脚本不复制、打印密钥，也不放宽容器入口设置的权限。数据库、应用
数据和 Codex 登录沿用现有命名数据卷。本入口包含完整策略执行链路；升级、
扩容前还需阅读分布式运行时部署指南。

## 行为与限制

- 桥接不发布主机端口，不挂载数据库凭据、券商账户、项目仓库或 Docker socket。
  可执行文件与脚本以只读方式挂载，登录状态存于独立数据卷。
- 每次请求都在空临时目录启动不持久化会话。忽略主机与项目的配置、规则，禁用
  shell、应用、浏览器、电脑控制、多代理及 code-mode 工具，使用只读沙箱。
- CLI 环境不继承 API Key 或内部桥接密钥；必须使用 ChatGPT 登录，拒绝 API Key 登录。
- 请求串行执行，避免同时刷新登录。失败不会自动切换到付费 API。此方式仅适用于
  可信本地使用，不适用于公共服务。
- 当前仅支持文本消息。JSON 通过 CLI 输出 schema 约束；流式界面会一次收到最终
  文本，而非逐 token 推送。
- 调用消耗当前 Codex 账户额度，登录有效期、限流和模型可用性由该账户决定。
  登录失效后重新执行设备登录命令。

停用时选择其他已配置供应商并停止 `codex-bridge` 即可。不会自动删除登录状态；
仅在明确撤销该接入时删除独立登录数据卷。
