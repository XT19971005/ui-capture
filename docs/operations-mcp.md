# 服务控制 MCP

拾界现在提供独立的 `Shijie Operations` Streamable HTTP MCP。结构参考 qprole，协议使用[官方 Python SDK v1](https://py.sdk.modelcontextprotocol.io/v1/)。业务容器关闭后控制服务仍运行；数据库不可用时身份校验拒绝访问，由宿主机管理员恢复。

| 工具 | 行为 |
|---|---|
| `get_project_status` / `diagnose` | 已部署 SHA、失败阶段、最近维护任务、容器状态及数据盘余量 |
| `get_job` / `get_logs` | 异步任务进度、退出码及脱敏日志；仅限拾界 web/worker/db |
| `control_service` | `operation=start/stop/restart`，`service=web/worker/all` |
| `backup` | 停写、备份数据库/工程/配置、校验后恢复原来运行的应用 |
| `deploy` | 发布已登记 origin/main 历史中的完整 40 位 SHA |
| `resume_deployment` | 按 `pending_commit` 继续同一次失败发布，保留备份 |
| `repair_deployment` | 以失败提交的后继版本修复；禁止改写已有迁移 |

所有写工具都接受 `request_id`，重试同一操作必须复用；改变参数需新 ID。断开 MCP 连接不会取消任务。维护期间拒绝另一个写操作；执行前检查拆图队列，未清空时拒绝停止、重启、备份和发布；允许启动 Worker 处理积压任务。没有任意 Shell、数据库停止/删除、GPU 控制或自动回滚数据库工具。

## 宿主机安装

Ubuntu 24.04 / Python 3.12 / Docker Compose / systemd，代码目录 `/opt/shijie/repo`，已部署配置 `/etc/shijie`。首次安装显式声明当前**真实运行**的提交和镜像，安装器会检查 Web/Worker 的镜像 ID 相同且匹配指定标签。不能用新拉取的 HEAD 冒充线上旧版本。

```sh
sudo ./shijiectl mcp-install --config-dir /etc/shijie \
  --deployed-commit 完整已部署SHA --deployed-image shijie:对应SHA标签
```

后续控制程序升级再次执行 `mcp-install --config-dir /etc/shijie`。已有任务正在运行时拒绝更新控制程序。安装不会更新业务版本、迁移数据库或修改共享 Nginx；两个 systemd 服务开机自启，不依赖业务 Compose 生命周期。

| 位置 | 用途 |
|---|---|
| `shijie-mcp.service` | 低权限账号 `shijie-mcp`，只监听 `127.0.0.1:8095/mcp` |
| `shijie-ops.service` | 宿主私有执行器，仅 Unix socket，没有 TCP 监听 |
| `/opt/shijie-control/current` | root 管理的独立控制程序快照与锁定依赖 |
| `/run/shijie-ops/control.sock` | 只允许 root 和 MCP 专用组访问 |
| `/var/lib/shijie-ops/jobs.sqlite3` | 任务、调用者、阶段、退出码及脱敏日志 |
| `/etc/shijie/deployment.json`、`pending.json` | 当前部署与失败恢复记录；不得手工删除 pending |
| `/etc/shijie/operations.json` | 固定仓库、远端、备份目录，不接受 MCP 参数覆盖 |
| `/etc/shijie/git-read.json` | 可选专用 Git 读取凭据，0600，不提交 Git、不放 URL |

Git 建议使用仅有 `read_repository` 的[项目 Deploy Token](https://docs.gitlab.com/api/deploy_tokens/#create-a-project-deploy-token)。私有文件格式为 `{"username":"专用用户名","token":"专用令牌"}`。仅向固定 HTTPS 拾界仓库发送，不跟随重定向；执行器不具有 Git 推送权限。成员的 MCP 权限与 Git 读取凭据分开。

普通 `shijiectl deploy/start/restart/stop/backup/status/logs` 在安装 MCP 后使用同一部署记录、不可变源码目录及互斥锁。`deploy --commit SHA` 可指定提交；省略时为已登记 checkout 的 HEAD，仍须在 origin/main 历史中。构建先于停写；升级失败保留备份与 pending。恢复后的源码和镜像不依赖 checkout 后续变化。未完成部署存在时禁止普通启停覆盖现场。

## 线上入口与身份

线上入口已启用：`http://47.117.156.236:8000/shijie-ops/mcp`。仅允许 qprole 当前登记的 `10.103.38.87`、`121.36.91.211`，通过现有 HAProxy PROXY protocol 得到真实来源；8095 只监听回环，其他服务的 IP 规则保持不变。

可信网关逐请求根据登录用户覆盖 `X-User-Email`、`X-User-Name`，不得使用所有人共享的管理员邮箱或透传用户任填身份。拾界查询自己的数据库，只有当前启用的超级管理员可用；普通账号/运维角色不授权，撤权立即生效。白名单内无身份只允许握手和静态工具目录。请求上限 64 KiB；错误来源 403、缺少身份 401、无权限 403、身份服务异常 503。

HTTP 未加密，身份头模式只信任已登记网关机器。其他来源即使持有 Token 或自填转发头也拒绝。日后使用 HTTPS 时可改为默认个人 Bearer Token 模式：

```sh
sudo ./shijiectl mcp-token admin@example.com --config-dir /etc/shijie
sudo ./shijiectl mcp-token reader@example.com --config-dir /etc/shijie --read-only
sudo ./shijiectl mcp-token admin@example.com --config-dir /etc/shijie --revoke
```

命令只打印私有凭据路径，不打印 Token；Token 模式同样检查当前超级管理员身份。不得通过公网 HTTP 发送个人发布 Token。

客户端选择 Streamable HTTP（MCP），地址填写上述入口；可信网关无须 Bearer Token，但实际工具调用必须注入当前用户身份头。查询状态后调用写工具，通过返回的 `id` 查询 `get_job`；`succeeded` 才表示完成，接收任务不等于发布成功。

## 验证命令

独立测试不需要个人 AI、生产数据或真实 Docker 写操作；临时 Git 仓库真实运行，Docker 由可记录调用的子进程替身替代。

```sh
uv sync --only-group mcp --python 3.12
uv run --only-group mcp python -m unittest discover -s ops_tests -t . -v
```

正式安装只读取 `deploy/mcp-requirements.lock` 的版本和哈希。业务容器不安装 MCP 依赖。测试报告应分别记录替身测试、Ubuntu 实测、线上发布结果以及尚未验证项。
