# Agent Gateway 快速开始

QuantDinger 在 `/api/agent/v1` 提供租户隔离的 Agent Gateway。Agent Token 与人类用户 JWT 相互独立，并受 Scope、市场与标的白名单、速率、有效期、模拟盘限制和名义金额上限约束。

## 1. 创建并验证令牌

在管理员界面创建 Agent Token，首次显示时立即保存完整值。先用最小权限验证身份：

```bash
curl -H "Authorization: Bearer $QUANTDINGER_AGENT_TOKEN" \
  http://localhost:8888/api/agent/v1/whoami
```

任何会产生副作用的 `W/B/N/T` 请求都必须带唯一的 `Idempotency-Key`。只有重试完全相同的方法、路径、查询和请求体时，才复用原键。

## 本地项目连接

本地 WSL 经操作者配置后，连接保存在仓库外的
`~/.config/quantdinger/agent.env`，目录权限为 `0700`，文件权限为 `0600`。
文件包含 `QUANTDINGER_BASE_URL` 和 `QUANTDINGER_AGENT_TOKEN`；不要显示或复制其内容。
同一 WSL 用户的 agent 和 worktree 可以通过启动脚本读取：

```bash
python scripts/with-agent-env.py python - <<'PY'
import json, os, urllib.request
request = urllib.request.Request(
    os.environ["QUANTDINGER_BASE_URL"].rstrip("/") + "/api/agent/v1/whoami",
    headers={"Authorization": "Bearer " + os.environ["QUANTDINGER_AGENT_TOKEN"]},
)
client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with client.open(request, timeout=15) as response:
    print(json.dumps(json.load(response), ensure_ascii=False))
PY
```

先核实返回的租户和权限限制，再执行其他调用。已安装 MCP 时可运行
`python scripts/with-agent-env.py quantdinger-mcp`，详见 [MCP 接入](MCP_SETUP_CN.md)。
显式环境变量优先；需要另一份私密配置时可设置 `QUANTDINGER_AGENT_ENV`。
新 worktree 要确保项目指引和启动脚本已经带入，未提交文件不会自动复制。
其他用户、机器或容器需单独配置已授权凭据；持有连接不代表获得新的下单或实盘部署授权。

## 2. 策略源码与部署

可执行策略使用 Strategy API V2。推荐流程：

1. `GET /strategy-sources/templates` 获取模板；
2. `POST /strategy-sources/compile` 编译检查；
3. `POST /strategy-sources` 保存私有源码；
4. 通过 `/strategy-sources/{source_id}/versions` 查看不可变版本；
5. 用已保存的 `sourceId` 创建停止状态的部署。

```bash
curl -X POST http://localhost:8888/api/agent/v1/strategies \
  -H "Authorization: Bearer $QUANTDINGER_AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: deploy-spy-trend-v1" \
  -d '{
    "name": "spy-trend",
    "sourceId": 12,
    "initialCapital": 10000,
    "executionMode": "signal",
    "leverageEnabled": false,
    "params": {"lookback": 50}
  }'
```

部署配置使用 `W` Scope；启动、停止或下单属于运行时行为，需要 `T` Scope 和额外服务端保护。

## 3. 提交回测

回测异步执行。提交后轮询 `/jobs/{job_id}`，或订阅 `/jobs/{job_id}/stream`。取消任务使用 `POST /jobs/{job_id}/cancel`，需要 `B` Scope、新幂等键以及 MCP 层确认。

## 4. 研究、指标与交易

- `/research/*`：点时点股票池、因子元数据和租户自选列表。
- `/indicators/*`：仅用于图表指标；指标代码不能直接提交到回测端点。
- `/trading/*`：返回脱敏的凭据元数据、账户快照、持仓、挂单和成交记录。
- `/notifications/signal-alerts`：管理信号提醒；立即评估可能触发通知，需明确确认。
- `/quick-trade/*`：快速下单和紧急停止，必须使用 `T` Scope。

实盘执行还要求服务端启用实盘、令牌允许实盘、提供凭据引用、客户端明确确认，并满足单笔和单日名义金额上限。

## 5. 上线前检查

- 先用模拟盘和最小 Scope 验证完整流程。
- 不记录 Token、API Key、Secret 或 Passphrase；脱敏值不可尝试还原。
- 对订单、通知、取消、恢复版本和紧急停止保留人工确认。
- 按 `429` 响应的 `Retry-After` 退避，不绕过共享速率限制。

完整字段和响应以 [Agent OpenAPI](agent-openapi.json) 为准；MCP 客户端配置见 [MCP 接入指南](MCP_SETUP_CN.md)。
