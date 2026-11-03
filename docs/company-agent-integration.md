# 公司 Agent 生图接入与当前阻塞

2026-10-22，本地 Ubuntu 24.04 Docker，配置模型 `gpt-6-astra`。仅使用测试色块和测试生成图片；没有对用户当前工程反复执行拆分，也没有修改公司平台或远程部署。

## 已实现并验证

- 分析和生图均通过 `POST https://zxty.tuyoo.com/aichat/v1/agent/chat`，Bearer 使用当前用户保存的公司 PAT。
- 请求 `message / model / sender_id / stream / files`；附件使用 `file_name / file_type / file_base64`。SSE `done.content` 是完整回复，不与 delta 拼接。
- 实测图片结果是 Markdown 下载链接，路由 `/aichat/v1/workspace/<workspace-id>/download?path=gen_image%2F<generated-file>`。同一 PAT 可下载，不使用网页登录凭据。
- 只允许该公司域名、已观察到的产物路由和 `gen_image/` 目录，不跟随重定向；拒绝路径穿越、其他主机、额外查询参数和伪装图片。下载上限 32 MB，最大 8192 边长/3600 万像素。
- Pillow 解码实际内容后保存 PNG；不透明 JPEG 可以无损于解码像素地规范化成 PNG，但不会把它冒充透明图。透明任务必须具有真正的透明像素，同时不能是全透明空图。验证完成后原子替换目标，错误保留原文件。
- 移除旧 `COMPANY_GENERATION_PENDING` 固定拦截。仅公司配置可入队，分析/生成都使用公司服务；双配置仍优先 Codex。不会因接口失败而切换提供方。
- 正式 `company_agent.generate()` 真实调用成功：1024×1024 PNG，Alpha 极值 255/255，provider=company，约 94 秒。原始协议及成品保存在忽略 Git 的 `.local/data/users/<当前用户>/ai-probes/`。

## 完整拆分尚未通过的外部依赖

### 1. 上传附件交给图像编辑工具时失败

两次小图附件编辑均失败。外层 `/agent/chat` 返回 HTTP 200 和完整 SSE，**是 Agent 最终回复报告内部图片 API 返回 400**，并非外层 HTTP 400。

最后一次严格按公司公开 `sys__media-generation` 说明使用 `operation=edit`、`images[].image_url`、`n=1`、`background=opaque`，只在测试红圆中添加一个蓝色小方块，不传入未公布参数。Agent 报告已引用本轮 `/workspace/upload/aichat-attachment-…`，图像编辑仍返回 400；未自动重试。此前还有附件路径无法被文件处理工具读取的报告。

已验证：将同一公司工作区**已经生成的图片下载 URL**作为参考可以完成编辑。因此应由公司平台检查 Agent API 的 base64 附件如何交给 media_generation：实际可读文件路径/可用 image_url、访问权限、工具参数和内部图片 API 的原始错误。

普通网页 `/v1/files` 上传接口不接受此 PAT（401），没有使用网页 JWT 或新增凭据绕过这个边界。

### 2. 请求透明背景实际仍得到 JPEG

文生图和以已有生成图片 URL 为参考的图片编辑均请求透明背景。后一次按公开工具说明使用 `background=transparent`。两份文件均实际下载并由 Pillow 验证为 **JPEG、RGB、1024×1024、没有 Alpha**，不是仅依据扩展名判断。

公开编辑说明列出 `background=auto/transparent/opaque`，未列出 `output_format` 或 `transparent_background`，也没有可直接指定图像模型的 `model` 参数。聊天的 `gpt-6-astra` 模型 ID 不保证其下游图像工具输出 PNG。

需要公司平台确认实际图片模型/路由是否支持透明 Alpha，并保证输出格式保留 Alpha。拾界不会以改扩展名、白底或棋盘格代替透明素材。

## 验证范围

自动检查使用本地伪造 HTTP 响应，覆盖真实观察到的 SSE/JSON/图片协议、下载信任边界、透明检查与失败保留；不调用真实 Key。实际探索单独使用当前账号配置和合成测试图，不属于自动测试。

本地接入已可处理生成图片；**完整拆分、真实原图提取和透明素材端到端仍未验收通过**。公司平台上述两项修复后，应先用小图验证，再执行实际工程。
