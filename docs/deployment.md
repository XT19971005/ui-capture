# Ubuntu 24.04 部署与恢复

## 目录与运行方式

应用使用 `deploy/Dockerfile` 的 Ubuntu 24.04 镜像；PostgreSQL 独立容器；Nginx 留在宿主。没有在容器内运行 SSH 或 systemd，日常管理通过 `shijiectl` 和 Compose 完成。Docker 安装及 Compose 插件按 [Docker 官方 Ubuntu 安装说明](https://docs.docker.com/engine/install/ubuntu/)操作。

代码目录放在 qprole 旁边；私有配置建议 `/etc/shijie`，数据建议与 qprole 一样放 `/home` 数据盘下的 `/home/shijie/data`。PostgreSQL 卷 `shijie_postgres` 位于 Docker 数据目录；部署前确认该目录的容量及备份策略。只对本机发布 `127.0.0.1:8093`，数据库端口不发布。

当前 Compose 上限为 Web 4 GiB、Worker 8 GiB、数据库 2 GiB，不是实测容量承诺。Worker 每次处理一个任务，每人最多 5 个待处理/执行中任务，默认任务上限 2 小时。没有承诺 100 人负载或并行 AI 推理能力；上线规模扩大前应测量真实图片、图层数和磁盘峰值。

## 首次准备

以下为目标机操作说明，本轮没有执行远程操作。将不含 `.local`、`.venv`、`node_modules`、`output` 的源码同步到 qprole 的同级 `shijie` 目录。不要复制本地会话和个人 Codex 登录。

```sh
cd /实际父目录/shijie
sudo ./shijiectl init --config-dir /etc/shijie \
  --data-dir /home/shijie/data \
  --public-url https://实际公司域名/shijie \
  --oidc-from /etc/qprole/config.toml
sudo ./shijiectl config --config-dir /etc/shijie
```

`--oidc-from` 可省略。它只借用登录端点、模式和传输选项，不复制 qprole 的客户端身份、密钥、管理员、数据库或个人数据。`init` 拒绝覆盖已有配置和接管非空数据目录。私有配置权限为 0600，生产应用使用 UID/GID 10001；如果在编辑时改变了文件所有者，恢复 `chown 10001:10001 /etc/shijie/config.toml`。

填写 `[oidc]` 的 `mode`、`client_id`、对应端点/密钥，以及 `bootstrap_admin_emails`。Broker 使用授权码和 PKCE；direct 使用发现文档及客户端密钥。首次管理员名单只影响新建账号，后续不会自动恢复已撤销的权限。登记**拾界自己的**回调：

```text
https://实际公司域名/shijie/auth/oidc/callback/
```

不要更换生成的 `[site].secret_key` 或数据库密码；`database.url` 与 `postgres-password` 必须匹配。`[storage].root` 是容器内 `/data`；`[deployment].data_dir` 才是宿主路径，部署后不要直接改目录来“迁移”资料。

将 `deploy/nginx.conf.example` 的 location 配置合并到现有 HTTPS server，检查域名、证书和 `/shijie` 前缀。代理保留路径，设置正确 Host 和 X-Forwarded-Proto。确认配置后执行 `nginx -t`，再 reload；不要覆盖同机 qprole 的 location。

```sh
sudo ./shijiectl deploy --config-dir /etc/shijie
sudo ./shijiectl status --config-dir /etc/shijie
```

部署会构建锁定依赖的镜像、等待数据库、停写、迁移、检查运行依赖/私有盘及正式登录配置，最后启动 Web/Worker。正式地址的 OIDC 占位符、缺少首次管理员、配置权限错误或磁盘不足会阻止完成部署。失败时查看日志并处理后重新执行；不要重新生成配置。

Python/npm 依赖由 `uv.lock`、带哈希的 `deploy/requirements.lock` 和 `package-lock.json` 固定。基础镜像固定多架构摘要；APT 安全包来自 Ubuntu 仓库，因此不承诺逐字节相同的镜像。当前实机验证为 Linux/arm64，远程 amd64 需在目标架构重新构建并运行同一套检查。

## 上线验收

1. 健康接口 `/shijie/health/live`、`/shijie/health/ready` 正常，Worker 容器持续运行。
2. 首次管理员通过真实公司 SSO；普通账号首次待授权，授权后进入，撤权后接口拒绝且在途任务取消。无默认密码入口。
3. 两个用户的工程、任务、浏览器恢复内容与 Codex 账号互不串用；管理员不能读取他人 AI 凭据。
4. 每人完成 Codex 设备码登录。工作区可能需要开启设备码授权；账号必须实际支持内置图像生成。流程参考 [官方认证说明](https://learn.chatgpt.com/docs/auth)和 [app-server 接口说明](https://learn.chatgpt.com/docs/app-server)。
5. 使用代表性素材验收拆分、部分失败续拆、精修、替换、原生文字/透明 PSD、浏览器关闭后找回任务。Linux 字体使用 Noto Sans CJK SC / Liberation Sans，与 Windows 商业字体可能存在视觉差异。
6. 执行一次完整备份与隔离恢复；检查磁盘高水位和任务超时策略后再开放入口。

预检和协议测试不等于真实公司授权或真实 AI 推理成功。不会借用开发者账号，也不以裁剪代替 AI 补全来冒充验收。

## 升级、停机和备份

升级前保留上一个代码版本及镜像。首次导入仓库后建议提交经过验收的代码，镜像另加可追溯标签。

```sh
sudo docker tag shijie:local shijie:before-upgrade
sudo ./shijiectl deploy --config-dir /etc/shijie --backup-dir /mnt/company-backup/shijie
sudo ./shijiectl logs --config-dir /etc/shijie
```

已有 Web/Worker 在运行时，`deploy` 强制要求备份目录，并在修改服务前备份，保持停写直到升级完成。备份目录不能在数据目录内部；应实际位于备份盘。运行中任务在停机时会中断并保留中间结果，不自动重放收费调用。

独立备份命令：

```sh
sudo ./shijiectl backup --config-dir /etc/shijie --backup-dir /mnt/company-backup/shijie
```

备份先停止 Web/Worker，导出 PostgreSQL，再打包数据、原配置和数据库密码，最后写入包含 SHA-256 的 `COMPLETE`。失败不写 COMPLETE，且保持写入服务停止。目录权限 0700；备份含个人 AI 登录及站点秘密，只能交给受控备份存储，不能作为可下载工程分发。成功后恢复 Web/Worker。

`restart` 仅重启应用，不执行迁移。日常 `stop` 不删除数据；不要使用 `docker compose down -v` 清理这个项目。

## 隔离恢复

恢复时必须使用同一个备份中的数据库、数据、配置和密钥。先恢复到**新目录及独立数据库**，保留现有资料；校验失败不要向生产目录解压。

以下 Python 3.12 命令验证 COMPLETE 并只向新的目标目录解包：

```sh
sudo python3 - /mnt/company-backup/shijie/具体备份 /home/shijie/restore-具体日期 <<'PY'
import hashlib, json, pathlib, sys, tarfile
source, target = map(pathlib.Path, sys.argv[1:])
manifest = json.loads((source / 'COMPLETE').read_text())
assert set(manifest) == {'database.sql', 'data.tar.gz'}
for name, expected in manifest.items():
    with (source / name).open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected, name
assert not target.exists(), '只允许新目标目录'
target.mkdir(parents=True, mode=0o700)
with tarfile.open(source / 'data.tar.gz') as archive:
    archive.extractall(target, filter='data')
print('校验及隔离解包完成')
PY
```

在现有 PostgreSQL 中创建全新验收库（先确认示例库名没有被占用），导入独立备份：

```sh
sudo docker exec shijie-db-1 createdb -U shijie shijie_restore_check
sudo docker exec -i shijie-db-1 psql -v ON_ERROR_STOP=1 -U shijie -d shijie_restore_check < /具体备份/database.sql
```

核对用户、任务和对应工程文件。上述 SQL 含 DROP/CREATE 表语句，**不要把验收库名换成现用库**。本轮已实际完成这种独立库恢复检查。

正式切回属于停机维护：停止 Web/Worker，备份当前状态，以验证过的恢复目录作为新数据目录，恢复备份中的私有配置/密码；将验证过的 dump 导入一个全新 PostgreSQL 实例的 `shijie` 库，再重建应用。若当前数据库 schema 已升级，不要只回退镜像而沿用新库。`shijiectl` 首版没有自动恢复/数据库切换命令；正式切换前需按目标机实际目录与卷安排维护窗口。保留旧镜像、旧数据库卷和旧数据目录，直到恢复后的登录、工程读取及代表性输出验收通过。
