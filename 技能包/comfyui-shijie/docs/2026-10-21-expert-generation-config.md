# 视觉专家生成配置加载顺序修复

服务器诊断运行：3285b1e9-ffd5-4633-a344-f42437143bdd。

实测异常链进入 `vision.run_expert -> from_pretrained -> adjust_generation_fn -> GenerationConfig.from_pretrained -> _dict_from_json_file`，报 NoneType 路径。

平台共享模型目录只保存大权重，校验过的配置/分词器由 install.py 放在节点包 model_support。原实现显式提供模型 config，却在 from_pretrained 返回后才提供 generation_config；Transformers 在返回前已尝试从权重目录加载生成配置。

修复：先从已验证配置目录离线读取 GenerationConfig，与模型 config 一起传入 from_pretrained。保留 local_files_only、trust_remote_code=False、原权重、dtype 和设备设置；不移动或重复下载权重，不修改平台隔离配置。

回归：独立模拟只有权重的目录，在模型加载调用时检查生成配置已传入；旧顺序实际失败，修复后通过。包括诊断调用点测试在内共64项本地回归通过。服务器实际推理结果另记，不能以本地回归冒充成功。

实际服务器验证：修复包 SHA256 `6eb6d9af5dee75275998fdd3637484bcbad425240d8cd382f491d5a4c5858f8b` 已安装启用。相同原图连续两次全流程4/4节点成功，运行 c72eb6e2-6d42-40c7-83dd-6ab193c1c8a4（总39秒，专家25.23秒）与 c4dd49dc-7093-498f-9075-6076d43f9c32（总29秒，专家15.80秒）。首个实际PSD独立回读为800×800、8层，其中7个原生文字层。该流程只是原图+文字的专家最小验证，不能冒充完整拆图成功。专家建议层数24、英文空格及忽略可见文本的建议仍需质量修正。

官方实现参照：https://github.com/huggingface/transformers/blob/main/src/transformers/generation/utils.py （GenerationMixin.adjust_generation_fn）。

部署注意：平台从ZIP文件名生成节点包身份；更新须保留原文件名“拾界_ComfyUI原生分层_安装包.zip”。改变名字会引入重复节点提供者，使候选引擎验证失败；失败保留原环境，不禁用验证。
