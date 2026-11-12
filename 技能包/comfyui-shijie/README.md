# 拾界 · ComfyUI 原生分层节点

在服务器本地执行，接收千问等模型的全画布 RGBA 图层，CPU OCR 输出文字方案，再将文字、纯色矢量和位图写入同一 PSD。节点注册不下载模型、不启动生成、不安装软件。

用户长期约定（2026-10-20）：ComfyUI全部使用开源模型、工具和节点，不接付费或闭源API。权重和新运行依赖仅在服务器下载、安装。图层数按内容决定；低Alpha阴影不是异常残影。

## 本地开源视觉专家
“拾界 · 本地开源视觉专家”使用 Qwen/Qwen3-VL-2B-Instruct（官方模型页标注 Apache-2.0），只在服务器推理。第一次运行从ModelScope或HuggingFace下载官方权重到 `ComfyUI/output/.shijie_models/LLM/shijie/Qwen3-VL-2B-Instruct`；之后可选“仅使用本地”。不启用trust_remote_code，不接受任意模型仓库或下载URL。不会把用户图片发给模型API。

原图同时接自动OCR和视觉专家；OCR方案接视觉专家的ocr_plan。专家的“拆分说明”接千问正向CLIPTextEncode.text，“建议分层数”接潜空间layers，“专家方案_JSON”接原生PSD的plan_json。解码后可接“拾界 · 看实际图层命名”，其输出再接导出layer_names；命名依据实际返回的层而非计划顺序。专家会在执行后释放GPU资源，供后续分层模型使用。下载、推理与艺术质量分别验收，未执行成功不声称专家已可用。

来源：[官方模型](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct)、[Transformers](https://github.com/huggingface/transformers)、[ModelScope](https://github.com/modelscope/modelscope)。未选Qwen2.5-VL-3B：该型号的研究许可证与本任务默认开源商用工具选择不一致，不把“可下载权重”当作通用许可。

## 安装
复制本目录到 ComfyUI/custom_nodes/comfyui-shijie，使用 ComfyUI 自己的 Python 安装 requirements.txt。服务器已有 Node.js 时直接使用；否则requirements从PyPI安装 nodejs-wheel-binaries 22.x，由同一ComfyUI Python环境运行，只用于本机PSD编码、不启动服务，也不要求系统管理员安装。纯JS依赖已包含，保留各自许可证，不需要 npm install 或 Windows canvas 二进制。可通过本平台 ZIP 节点包入口安装，安装会影响公共服务器节点环境，须明确确认后执行。

## 接线
1. 原图 LoadImage → 拾界 · 自动文字分析 → 专家方案_JSON。
2. 原图 → 既有千问分层流程 → VAEDecode 的 RGBA IMAGE → 拾界 · 原生文字矢量PSD 的 layers。
3. 专家方案_JSON → 导出节点 plan_json，选择服务器已有字体，项目名按原图命名。批量图层名称每行一个。
4. 首次保留默认“位图原文字”，确认 OCR 内容/框/颜色后才能开启 replace_text 去重，否则可能损伤原画。此版不声称无需确认的一键精确恢复。
5. Run 输出到 ComfyUI/output/拾界/项目名；同名再次运行使用新序号，PNG、PSD、检查记录平铺同一目录。节点不创建前端工程库记录。

图层数不固定：专家按实际内容返回 suggested_layer_count，接“拾界 · 按内容取分层数”的 INT 输出到千问 EmptyQwenImageLayeredLatentImage 的 layers 输入，替换旧的固定8层。OCR节点只负责识别文字，不冒充视觉专家推断实体层数；未给出分层建议时明确报错，不能偷偷回落为8层。最终PSD叶层数随真实位图、文字及形状数量变化。

已包含 OFL 授权的 Noto Sans SC 开源字体及许可证（来自 Google Fonts 官方仓库），确保Linux服务器能选择中文字体。它不等于原图同款字体。

## 专家接入
可将 expert/拆图专家.md 中的结构要求交给平台 Skill 专家，返回纯JSON传入“拾界 · 专家方案”或直接连接STRING。Skill本身不会生成原生层，必须连接本包导出节点。外部模型节点由用户自己的平台配置决定，本包不发送外部请求。

## 能力边界
- 原生文字：有字体、内容、字号、颜色与变换矩阵，Photoshop可编辑；不是OCR字符串旁挂一张假文字PNG。字体匹配仍需确认，弯曲/竖排/明显倾斜文字暂保留位图并告知。
- 原生矢量：仅将整张图层的单色不透明核心拟合为连续Bezier形状，轮廓包含孔洞；多色、渐变与低透明度阴影保留RGBA。不是所有图都强转矢量。
- 去重仅在明确文字框内处理与文字颜色匹配的像素；不改变框外。混合层与细小文字仍须检查。
- PSD 明确写入合成图和JPEG缩略图；测试分别验证原生描述、透明度、预览。客户端真实编辑和资源管理器显示需要独立验证。
- 本包负责后处理，不替代人物/背景分层模型，不保证拆开龙和锦鲤等相互遮挡实体。

## 测试
python -m unittest discover -s tests -v

独立只读验收：使用已有 psd-tools 环境运行 `python audit.py <PSD路径> --requirements <验收要求JSON> --output <检查JSON>`。不下载依赖、模型，不生成检查图片，不修改源文件。核对编号 PNG 与图层、原生文字（保留空格）、原生形状数量、缓存合成与独立合成；低透明层不按 Alpha 低自动拒收。独立合成允许最高 3/255、平均 0.5/255 的舍入差，完整记录误差。结构通过仍显示 `visual_status=NOT_CHECKED` 和 `final_acceptance=NOT_GRANTED`，必须另行实际看图。

自动OCR采用 RapidOCR ONNX；Bezier拟合复用本地 game-ui-to-psd 工具，副本为本包内部模块。JS依赖：ag-psd 31.0.3 (MIT)、svgpath 2.6.0 (MIT)、base64-js 1.5.1 (MIT)、pako 2.1.0 (MIT/Zlib)，许可证在vendor目录。安装缺Node会在导出前明确报错，不能标记成功。


ComfyUI结果存放补充（用户2026-10-20明确）：测试版本集中在编号测试目录，已自检不合格的版本集中在不合格目录；每版按生成顺序编号并写明验收状态，根目录明确标出最新版本及位置。只有实际自检合格的最终结果放在外层，不能把最新测试版或未验收版命名为最终版。没有合格成品时明确写“暂无合格最终成品”。安装包与图像结果分开。


## 三条分支先处理，再重组（2026-10-20）
完整模板：example_workflows/专家_文字矢量图片三路重组.json。
1. 专家分析与OCR：原图进入服务器本地视觉专家，按实际图片输出实体、校字、文字/艺术字分类及图片分层数。
2. 文字线：先在原图去字，再把干净输入交给图片线；普通文字在服务器已有字体中按真实字形蒙版IoU匹配。匹配不足保留原像素待修，不拿错误字体冒充合格原生文字。
3. 矢量线：从原图单独提取纯色艺术字/图形轮廓与孔洞；检测真实原始颜色变化，渐变、纹理、阴影保留位图并提示，不能先涂平再谎称纯色。
4. 图片线：仅接清理后的图片，按完整实体拆分；龙与鲤鱼组合含完整鱼尾，扇子不能混到主体。现有模板仍使用Qwen图层模型，提示词不保证模型一定遵守；缺件、混层需实际看图拒收。
5. 三路重组：原画布坐标校验，直接写入真正native text、native shape和pixel层，不再做一次OCR叠加。输出专家方案、字体匹配分数和失败警告，运行完成不是画面验收通过。

### 同款底稿复用节点（源码完成，服务器尚未部署）
`拾界 · 同款底稿复制实例` 接收图片分支RGBA与实例JSON。保留全部源图层，为每个实例输出独立RGBA和层名，再连接重组节点；不调用生成模型、不因低Alpha删除阴影。只支持平移与等比缩放，使用预乘Alpha缩放防黑边；越界、无效索引、重名、未验收源素材明确报错。它不会自行把同类型素材判为同款。

实例JSON示例：`[{"source_index":0,"source_review":"PASS","name":"宝箱_第二处","x":134,"y":330,"scale":1}]`。索引从0开始，x/y为复制后可见Alpha边界的左上角，非完整透明画布原点。单写PASS不能通过：还须连接当前original原图、source_reviews与source_sha256（原图摘要采用shijie_contract.asset_digest对当前RGBA像素计算），记录实际源素材RGBA摘要、原图摘要、visual_reviewed=true、空issues和拾界六项逐条观察。素材变化会使旧验收失效。校验器只核验记录绑定，不替代实际看图；实例位置仍须逐个验收。例子仅示意接口，不是森之鹿灵已确认的素材索引或位置。形状、颜色、角度不同的素材分别处理。

### 复用拾界源码
shijie_source保留拾界现有纯组件规划和验收约束；来源与摘要见docs/拾界源码迁移来源.json。开发者可显式运行sync_shijie_contract.py刷新，经审查后才发布；服务器不自动读取本机项目或运行迁移。原来的模型客户端没有迁入，不接闭源API。完整能力差距见docs/拾界能力迁移清单.json；迁入校验不等于完整插件功能已接通或画面通过。
专家权重由平台正式模型准备通道下载到共享 /models/text_encoders/shijie/Qwen3-VL-2B-Instruct/model.safetensors；计算节点仅本地读取。配套配置与分词器由服务器 install.py 安装并校验官方摘要，不在本机下载。平台当前拒绝含安装脚本的更新，明确要求运维启用 workspace.node_environments 并重启 models worker；不能绕开此限制。权重就绪不等于专家推理或 PSD 验收通过。
