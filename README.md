# AI拆图助手 · 服务器版（shijie）

将“拾界_便携分享版”的拆图内核与编辑器迁移成独立、多用户 Web 服务。目录与 `qprolevideopipelineweb` 同级，结构、公司登录、角色授权及部署方式参考 qprole；原工程和 qprole 保持不变。

本地与远程均运行 Ubuntu 24.04 应用容器：Django / Gunicorn 提供页面和接口，PostgreSQL 保存身份与任务，一个独立 Worker 最多并行执行两个任务（同 Codex 账号、同工程与本机 GPU 互斥）。原编辑器继续负责图层编辑及 PSD 导出；没有新增 Redis 或 Celery。

## 本地启动

宿主需要 Docker（含 Compose v2）和 Python 3.11+；应用及原生图像依赖全部在容器内安装。

```sh
cd /实际父目录/shijie
./shijiectl dev
./shijiectl status
```

访问 <http://127.0.0.1:8093>。首次启动生成独立随机密钥、数据库密码及 `.local/config.toml`。开发环境使用源码挂载，Web 自动重载；修改 Worker 后运行 `./shijiectl restart`。

### Mac 本机透明分层（试用）

Apple Silicon 上可原生运行 Qwen-Image-Layered，业务仍在 Ubuntu Docker 中。使用官方 Diffusers 流程和 BF16 权重；当前未采用社区 MLX 移植。模型运行环境与业务 Python 隔离，依赖版本和模型 revision 固定在 `tools/local_model.py`。

```sh
./shijiectl model-download  # 首次下载约 57.7 GB 权重，可中断后继续
./shijiectl model-start
./shijiectl model-status
# 不使用时释放模型进程：
./shijiectl model-stop
```

宿主需安装 `uv`。首次使用会建立独立 Python 3.12 推理环境。更新本地 Compose 后运行一次 `./shijiectl dev`，加入 `.local/local-model` 的私有目录挂载。原生模型服务与应用通过此目录交接任务，不开放网络端口；Web 只读，Worker 写入请求。部署配置没有挂载此本机队列，远程 Ubuntu GPU 推理不在本轮适配范围。

页面顶部“AI 连接 → 本机模型”可检查状态；也可在“开始拆分”旁选择“本机分层 · 试用”。这是一项显式选择，原有自动模式仍按 Codex 优先、其次公司 Agent 的规则工作。其他生图、精修功能仍走原有连接。本机模式暂不接受已有部分拆分工程续拆，避免覆盖保留下来的图层。

试用参数为 640 分辨率档位、3 个图层（含背景）、20 步、固定种子 42。输出 RGBA 图片层，原图完整保留；文字尚未重建为文本，输出像素尺寸会记入工程 `recognition.generatedSize`，不能视为原图分辨率的无损恢复。结果标记“未检查”，需要核对透明边缘、重合效果和遮挡补全。

2026-10-22 在 M4 Max / 128GB 上完成一次网页到本机模型的真实测试：2384 × 1258 原图输出 3 个 896 × 480 图层，2 层含真实透明通道；模型运行 27 分 19 秒（加载约 88 秒），网页总耗时 27 分 26 秒。去噪回调记录到的最大 MPS 驱动分配为 85.1GB，此值不是整台机器的内存峰值。网页导出的 PSD 经 psd-tools 重新读取，3 个图层及透明通道保留。样例中人物、小鸡和牌桌仍合并在同一层，背景出现重绘纹理；当前适合作为试用基线，不能替代逐对象、原尺寸、可编辑文字的精细拆图。实测文件在本机 `.local/model-benchmark/`，不进入仓库。

模型服务串行处理任务，执行进程按任务启动、结束后释放内存。停止、超时、撤权和取消会停止本机推理；服务重启不会重跑已中断任务。状态和日志在 `.local/local-model/`，单次推理的日志、输入和结果在其 `jobs/<uuid>/` 下，均不进入 Git、Docker 镜像或云端 AI 请求。这里的诊断副本目前需管理员在任务结束后自行归档清理；应用工程仍在原来的个人工作区。

本地仍使用公司统一登录。运行 `./shijiectl config` 填写拾界专用 `client_id`、公司 Broker/OIDC 地址及 `bootstrap_admin_emails`，再重启。默认没有密码登录、测试账号或免登录入口。公司需要登记本地回调 `http://127.0.0.1:8093/auth/oidc/callback/`；若不允许回环回调，请使用公司批准的开发 HTTPS 地址。

公司登录与 AI 连接分开。进入工作台后，点击顶部“连接设置”，可分别保存 **公司 Agent** 和 **Codex**。

OpenAI 平台密钥使用 **连接设置 → Codex / OpenAI → OpenAI API Key**，点击“验证 API Key 并连接”。此入口通过 OpenAI `/v1/models` 验证鉴权（需要 Models 读取权限），再使用已安装 Codex 的 API Key 登录方式；分析和生图沿用 Codex 流程，按 OpenAI API 用量计费。鉴权通过不保证模型额度和实际生图权限，任务仍会检查结果。团队访问令牌与设备码登录仍保留，三种 Codex 认证方式共用当前用户的私有 Codex 凭据；更新失败保留旧凭据。密钥不进入工程、日志、命令行或浏览器存储。

自动选择：仅配置公司 Agent 时使用公司 Agent；仅配置 Codex 时使用 Codex；两者均配置时优先 Codex。提供方在任务提交时固定，默认分析与生图使用同一来源；新版可显式选择太石理解或亿创生图，选择相互独立；Codex 凭据失效或网络失败不会自动切换公司 Agent 重发。

**公司 Agent** 参照 TYComfyUI 的 `https://zxty.tuyoo.com/aichat/v1/agent/chat`，填写个人 API Key 和可用的视觉模型 ID。Key 按拾界用户加密保存，更新时留空保留；可停用连接而保留 Key。保存不调用模型，“测试图片分析”才发送一次 32×32 测试色块。图片分析支持 SSE 和同次请求的 JSON 回复；生图已接入同一 Agent 的真实工作区下载链接，校验公司域名、产物目录、图片内容和透明通道后原子保存 PNG。不会自动重发或改用另一服务，不合格产物不覆盖已有图片。注意：分析测试通过不代表图片编辑和透明输出已通过；本次实测文生图成功，但公司图像工具请求透明背景仍返回 JPEG，上传附件也出现无法供编辑工具读取的问题，完整拆分尚未验收通过。

Codex 保留两种连接方式：

- **团队访问令牌**：Business / Enterprise 成员可在 [ChatGPT 访问令牌管理](https://chatgpt.com/admin/access-tokens) 创建具有 Codex 权限的令牌，粘贴到拾界并点击“验证并连接”。工作区需要允许访问令牌及本地 Codex；没有入口时请联系工作区管理员。令牌通过 CLI 标准输入验证，先在临时账号目录确认连接，成功后才替换当前用户的凭据。HTTP/HTTPS 部署均可提交，不保存到浏览器或工程；HTTP 传输不加密。参见 [官方权限说明](https://learn.chatgpt.com/docs/enterprise/access-tokens)。
- **设备码登录**：点击“获取设备码”，复制大字显示的码，打开官方登录页授权。支持重新获取、取消、重开窗口恢复和自动检查；检查连接不会覆盖设备码。团队成员需要工作区管理员允许设备码登录。参见 [官方认证说明](https://learn.chatgpt.com/docs/auth)。

两种 Codex 方式都使用当前拾界用户自己的权限；登录后还需实际提供图像生成能力才能拆图。未连接或缺少图像生成时会在提交前明确提示，保留原图和编辑内容。服务不会自动读取宿主开发者的 Codex 登录。

## 美术版 20261102 能力合并

新增原图/单图层独立标注、连续 AI 助手、指定层拆分与再拆层、主画布候选对比、透明素材提取、背景清理及上下扩建、2:1 参考创作。标注是工程元数据，不写入原图或导出像素；生成候选须确认后应用，可撤销。原公司 Agent 与 Codex 保留，自动模式仍优先 Codex。

顶部理解/生图选择分别配置；新增太石理解、亿创 Matrix 生图。密钥只在当前拾界账号内使用，不读取其他应用的配置。新通道完成协议和隔离检查，未配置真实账号的通道不作为生图成功验收。

开发源码与运行副本统一通过以下命令构建（运行服务本身无需 esbuild）：

```sh
npm ci
npm run build
```

[本次深度对比、合入范围与实测结果](docs/upstream-20261102-comparison.md)。

## 本机版 20261104 增量更新

统一界面名称为“AI拆图助手”，仓库、URL、内部标识和既有数据目录保持兼容。合入关键节点保存、聊天与待确认候选恢复、共享图片撤销快照、透明素材内容边界与PSD透明留白精简、助手布局和字体批量替换。恢复候选只提供预览入口，不自动应用或重新生成；局部替换候选保留完整拆分基准与隐藏旧版本。反馈仅在本人确认提交后保存到个人私有目录，使用现有登录与CSRF保护。

官方远程仓库为 `https://tygit.tuyoo.com/qp_agents/shijie.git`（SSH：`ssh://git@tygit.tuyoo.com:2222/qp_agents/shijie.git`）。推送代码与服务器部署分开核验；当前仓库没有随附自动部署流水线。升级按 `docs/deployment.md` 先备份再部署，不复制本机凭据与工程。

## 使用及数据

- 导入图片或原有工程，拆分、续拆、精修、局部替换、生图、编辑图层，拖动、输入及生成进度仅标记未保存；生成完成、确认应用、取消保留结果、程序内关闭或切换工程/页面时保存，也可手动保存或导出 PSD。保存失败保留页面并阻止切换。
- 关闭页面后任务继续；从“任务记录”重新打开结果。执行中断不自动重发收费请求。尚未生成图层时可找回任务原图。
- 工程、任务与个人 AI 登录按用户划分；账号撤权后停止受理，运行任务会取消。管理员沿用 qprole 的授权规则。
- 保存使用版本冲突检测。旧版本覆盖返回 409；空间不足和写盘失败返回 507，保留已有工程。任务删除需明确确认，不影响另行保存的工程。
- `.local/data/users/<id>/` 保存个人工程、任务与 Codex 登录；PostgreSQL 使用独立卷 `shijie_postgres`。这些资料不进入 Git 或镜像。公司 Key 以 `company-agent.json` 密文保存，新模型来源 Key 以 `model-connections.json` 按用户加密保存，解密后只经标准输入交给选中的任务进程，不写入任务文件、命令行或环境；部署备份需保留原 Django `SECRET_KEY`，更换后应重新保存公司 Key。
- 保留原本的工作图缩放行为和原文件字节。服务端单张输入上限 6000 像素边长、600 万像素，单请求上限 276 MiB；超限明确拒绝。

原浏览器扩展、Figma 安装器和交互式第三方网页抓取未迁入服务器；已有网页工程仍可导入编辑。网页抓取 API 返回明确不可用提示。Figma 格式导出仍需原来的 Figma 导入插件。

## 结构

```text
shijie/
├── config/                Django 设置、URL、传输校验
├── shijie/accounts/       qprole 风格的 OIDC/Broker、权限与会话
├── shijie/pipeline/       私人工程、持久任务、Worker
├── shijie/templates/      公司登录和任务/授权页面
├── shijie/static/server/  同源接入和服务页面脚本
├── legacy/                原编辑器、拆图内核和 PSD 工具
├── deploy/                Ubuntu 镜像、Compose、配置及 Nginx 示例
├── shijie_ops/            独立服务控制 MCP、私有执行器和发布保护
├── tools/                 隔离执行入口及健康检查
├── tests/                 服务边界与现有编辑语义检查
├── docs/                  迁移分析、部署和验收记录
└── shijiectl              启停、构建、配置、测试、备份
```

## 验证与部署

```sh
./shijiectl test
./shijiectl logs
./shijiectl backup --backup-dir /绝对路径/备份目录
./shijiectl stop
```

[迁移分析与约束](docs/specs/migration.md) · [Ubuntu 部署与恢复](docs/deployment.md) · [服务控制 MCP](docs/operations-mcp.md) · [验收记录及待验项](docs/verification.md)

本地服务已完成公司 SSO、Codex 真实分析/生图、编辑及导出验收。新通道真实账号和复杂图保真仍有待验项，详见最新美术版合并报告；远程 Ubuntu 部署说明保留在 `docs/deployment.md`。
