# UI元素与结构知识

维护日期：2026-10-15，配套技能2.35。用于忠实拆分截图、规划原生文字/矢量/位图和检查组件完整性；不是重新设计指南，也不代表已学完所有游戏UI。本文件是知识目录，规则按当前原图证据应用，不把某个设计系统的默认外观套给游戏。

本文的“官方事实”来自下列一手资料；“本项目规则”是据此结合实际缺陷形成的拆图约束。知识、实现、离线验证、网页操作与艺术质量分别记录。新增类别先补真实样例和来源，不用不断扩大的术语表代替看图。

## 对象、图层、组件与实例

官方事实：Figma将主组件与可复用实例区分，实例关联主组件；组件可以是按钮、图标，也可以是更大的布局。相似组件可组成variant集合，以状态、大小等属性区分，各variant有自身属性组合。[组件](https://help.figma.com/hc/en-us/articles/360038662654-Guide-to-components-in-Figma)、[Variants](https://help.figma.com/hc/en-us/articles/360056440594-Create-and-use-variants)

官方事实：Photoshop图层承载独立可编辑内容，组用来组织相关图层，也能共同应用蒙版或调整。[图层与组](https://helpx.adobe.com/photoshop/desktop/create-manage-layers/create-layer-compositions/create-layers-and-layer-groups.html)、[组的用途](https://helpx.adobe.com/photoshop/desktop/create-manage-layers/get-started-layers/organize-layers-with-layer-groups.html) 本项目推导：组本身不证明里面的内容属于同一物理实体。

本项目按以下关系登记，不能相互替代：

- 语义对象：原图中可辨认的按钮、金币、标题、角色等，有自己的身份和作用。
- 绘制叶层：实际承载文字、路径或图片的最小可编辑节点；一个语义对象可有多个叶层。
- 绘制组：承担组织、实际层序、变换或蒙版关系；不是“同框即同物”的证据。
- 完整实体：确属一体且需要完整提取的角色、字标或物件。`entity_id`关联的是这一实体；相邻但独立的按钮与金币不共享它。
- 组件家族：结构/用途相似的控件集合，用`familyId`表达候选关系；实例仍各有独立节点、坐标、文案和槽位。家族不是完整实体。
- 变体与观察状态：颜色、材质、尺寸、选中/禁用等差异保留；蓝紫底板不能因形似混用。截图没显示交互的状态记unknown，不凭灰色就断言disabled，也不虚构hover。

同一人物与明确一体服饰/坐垫可属于完整实体；一排按钮则是多个组件实例。不能为了省调用把整排当一张完整素材，也不能为了多层把同一角色切成碎片。实例引用同一资产候选，不等于把多个位置合并到同一实体。

## 层序、遮挡与蒙版

官方事实：SVG采用画家模型，后绘制内容可能遮住先绘制内容；组透明度、蒙版等涉及组合后的绘制。`paint-order`调整单个元素内部填充、描边和标记的顺序，不改变相邻对象的堆叠顺序。[SVG渲染](https://www.w3.org/TR/SVG2/render.html)、[SVG绘制](https://www.w3.org/TR/SVG2/painting.html)、[paint-order](https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Attribute/paint-order)

官方事实：Unity uGUI同一Canvas下的UI按层级顺序绘制，后面的同级元素在前面的上方；多个Canvas另有排序机制。[uGUI Canvas 2.0](https://docs.unity3d.com/Packages/com.unity.ugui@2.0/manual/UICanvas.html) 本项目推导：不能把这一局部规则扩大成所有游戏渲染器的通用z规则。

官方事实：Photoshop图层蒙版控制图层或组的可见区域；矢量蒙版用路径定义边界；剪贴蒙版由基底图层内容约束上方图层。[图层蒙版](https://helpx.adobe.com/photoshop/desktop/create-masks/layer-masks/add-layer-masks.html)、[矢量蒙版](https://helpx.adobe.com/photoshop/desktop/create-masks/layer-masks/mask-layers-with-vector-masks.html)、[剪贴蒙版](https://helpx.adobe.com/photoshop/desktop/create-masks/layer-masks/create-and-manage-clipping-masks.html) 本项目推导：三者不能仅按“同组”互换。

本项目规则：先画遮挡关系再定从后到前的实际顺序，背景居底；不按面积、识别类别或检测框大小排序。半透明叠放、裁切窗口、同组透明度都要独立确认；解组会改变合成且不能无损迁移时明确拒绝。将背景去件与前景补全分别核对，不能用蒙版掩盖被裁断的完整底稿。

独立前景按边界和遮挡判断，底部、大面积、浅色都不是背景证据。明确纯色的独立云形/台面可用原生矢量，干净背景也须去掉它；无边界证据不凭空发明平面。新规则不会自动重拆旧工程，必须由用户主动处理具体问题。

## 文字、段落与完整字标

官方事实：Photoshop点文字以输入点起排，段落文字在限定框内自动换行；Figma文字框的自动宽度、固定框与缩放有不同效果，改变框尺寸不等于改变字体大小。[点文字与段落文字](https://helpx.adobe.com/photoshop/desktop/text-typography/type-layers-creation/create-point-type-and-paragraph-type.html)、[Figma文字尺寸](https://help.figma.com/hc/en-us/articles/27378154668951-Adjust-text-dimensions-and-resizing)

官方事实：Canvas文字的advance宽度和实际墨迹边界不是同一度量，斜体可能伸出advance范围；实际上下界相对基线度量。[TextMetrics](https://developer.mozilla.org/en-US/docs/Web/API/TextMetrics)

本项目规则：文案、字形、字号、实际墨迹、基线、段落框和换行共同核对。不能把检测框高度直接当字号，不能用横向拉伸补字体不匹配；多行逐行测量，以最长行和整体行高拟合并保留源框锚点。OCR内容不确定先标待校对，确认错误不能仅调样式后宣称修好；空白、字距、旋转方向和显式换行也属于内容。

字标先确认完整身份与全部字形。确属同一多色字标时作为一个语义实体，保留各真实颜色和可编辑子路径；不把每个颜色都当独立物件，也不能把多色强行压成单色。纹理/绘画艺术字保留完整位图底稿；普通文字尽量保持可编辑。把错误OCR、残缺轮廓或重复字片套进组，不构成实质修正。

## 路径、孔洞与抗锯齿

官方事实：SVG路径可含子路径和曲线；fill-rule的nonzero与evenodd以不同方式判定内部区域，影响孔洞及自交形状。fill-rule用于路径填充，SVG文本有自己的字形处理规则。[路径](https://developer.mozilla.org/en-US/docs/Web/SVG/Tutorials/SVG_from_scratch/Paths)、[fill-rule](https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Attribute/fill-rule)、[SVG文本](https://www.w3.org/TR/SVG2/text.html)

官方事实：Photoshop形状模式创建含填充及矢量蒙版的形状，单纯路径本身不等于已绘制的形状，像素模式是栅格内容。文字抗锯齿通过边缘像素的部分覆盖形成平滑过渡。[绘制模式](https://helpx.adobe.com/photoshop/desktop/draw-shapes-paths/draw-lines-curves/understand-shapes-paths-and-drawing-modes.html)、[文字抗锯齿](https://helpx.adobe.com/photoshop/desktop/text-typography/get-started-with-text/apply-anti-aliasing-to-a-type-layer.html)

本项目规则：一个真实单色标识优先一条含必要子路径的原生path；孔洞、孤立微点、细笔画和孔内小岛都须保留，不能把evenodd当作任意多路径的自动并集。多色实体按真实颜色分叶层并保持整体身份。正常曲线拟合连续贝塞尔并减少冗余点，手工毛边按源风格保留。

边缘从前景到背景的抗锯齿色阶不自动成为第二对象或独立颜色素材；但稳定的次要颜色、斜细线、小岛也不能被“去抗锯齿”抹掉。逐细连通区域核对，不用色数、5×5内核或整体相似率替代检查；新增毛刺要修，来源固有纹理要留。

## 布局、九宫格与复用

官方事实：Figma Auto layout通过方向、间距、内边距、对齐和尺寸策略组织内容，可嵌套；Hug、Fill和Fixed表达不同尺寸行为。[Auto layout](https://help.figma.com/hc/en-us/articles/360040451373-Guide-to-auto-layout-in-Figma) 本项目推导：单张截图只呈现一个结果，不能证明它使用了某种布局约束。

官方事实：Unity九宫格把sprite分成九区，Sliced保留角、按方向伸展边及中央，Tiled可重复部分区域。[Unity 6九宫格](https://docs.unity3d.com/6000.0/Documentation/Manual/sprite/9-slice/9-slicing.html)

本项目规则：九区不等于九个语义素材；截图无边界/重复证据时不虚构九宫格参数，也不宣称已支持九宫格导出。登记底板、图标、文案、数值及辅助槽位，避免只识别醒目图标漏底板或数字旁金币。相同底稿与共享文字样式可登记复用候选；各实例仍可独立编辑，实际复用前确认状态、方向、材质、颜色、裁切与遮挡一致。

同款资产可共享来源字节或一次提取结果，不同变体各保留自己的来源。代表样本检查后还要核对每实例位置、缺件与遮挡；“识别复用候选”不等于已经实现跨实例生成缓存或省去所有实例验收。

## 设计系统提供的解剖线索

以下是类别与槽位参考，不是强制套版；游戏装饰、货币、角色、艺术字等可独立登记，无法归类时保留未知。

- Material Web：按钮由标签及可选图标组成；列表有独立item，含主文案、辅助文案和起止内容；文本框区分标签、值、前后内容、辅助/错误文字。读取官方实现文档，不以不可读的M3页面外壳冒充全文学习。[按钮](https://raw.githubusercontent.com/material-components/material-web/main/docs/components/button.md)、[列表](https://raw.githubusercontent.com/material-components/material-web/main/docs/components/list.md)、[文本框](https://raw.githubusercontent.com/material-components/material-web/main/docs/components/text-field.md)
- Fluent：按钮承载动作，普通、切换、菜单、分裂按钮用途不同；卡片可有header/body/footer及媒体/动作；Tablist切换相关内容类别，不能与执行动作的按钮混为一谈。[按钮](https://fluent2.microsoft.design/components/web/react/core/button/usage/)、[卡片](https://fluent2.microsoft.design/components/web/react/core/card/usage/)、[Tablist](https://fluent2.microsoft.design/components/web/react/core/tablist/usage/)
- Carbon：输入框区分label、field、value、helper；通知区分图标、标题、正文、关闭及可选动作，并有不同消息状态。[输入框](https://www.carbondesignsystem.com/building-blocks/core/components/text-input/guidelines)、[通知](https://www.carbondesignsystem.com/building-blocks/core/components/notification/guidelines)
- Apple HIG：本轮仅取得官方检索内容，直接页面为JS外壳，未宣称通读HIG。Tab的导航与按钮动作区别只作补充，主要依据以上可读官方全文。[Tab bars](https://developer.apple.com/design/human-interface-guidelines/tab-bars?changes=l_1__4&language=objc)、[Buttons](https://developer.apple.com/design/human-interface-guidelines/buttons?changes=latest_1__8)

本项目已落地的源码映射：`uiComponents`登记实例ID、category、familyId、variant、observedState、parentId、evidence及slots；evidence记录非空观察或证据不足原因，槽位引用原assets/texts/vectors节点ID。类别为button/toggle/input/selection/navigation/list/list_item/card/panel/dialog/feedback/progress/badge/unknown；观察状态为unknown/default/selected/disabled/pressed/focused/loading/error/success。槽位为container/label/icon/leading/supporting/trailing/value/indicator/media/action/decoration。父组件通过parentId表达嵌套，不重复占用子组件叶节点；没有组件证据可用空数组，不为套模板补对象。

`uiReuseGroups`以asset或text_style、memberIds和evidence记录复用候选，状态为CANDIDATE_NOT_APPLIED；`recognition.uiStructure`中的reuseStatus为PLANNED_NOT_APPLIED，linkStatus为RESOLVED或PARTIAL。引用、父循环、重复归属、跨命名空间ID和实例合并须校验。组装后链接到真实scene节点，多色艺术字可一对多链接当前path且排除隐藏旧版；用户删除的native在续拆时只标未解析，不凭组件元数据重建。本段是本项目源码接口，不是Figma/Adobe标准；19项组件专项及本轮后端338项离线回归通过（排除3个浏览器模块）。实际新鹿规划的11个组件/6组复用候选已保存，本地draft组装UI映射全resolved，但54个位图仍待生成，不是画面验收。资产自动复用尚未实现，仍逐实例生成，不重新套用官方字体样式。

## 应用与证据压力场景

先读原图并列语义对象、槽位及未知项，再定完整实体、真实遮挡与蒙版，选择文字/矢量/位图表达；规划结构与来源完整后才提取或修正。复用与联合实体必须有明确图像证据；本项目联合实体置信度门槛为至少0.9，这是项目门槛，不能标成官方标准或靠同框猜测凑数。证据不足保持原状并说明，局部修正不能扩成全图重生成。

以下9题已由final_review进行只读规则评估，判定规则表达清楚；这是规则评估，不是执行拆图、VLM或艺术质量测试。联合路径离线专项Python71项通过/5项既有opt-in跳过、Node46项通过；真实网页4路径联合检查通过结构保持，保留原path值与17个未选中节点，字形未修仍NEEDS_REVIEW。结构关联成功不证明原图覆盖或艺术质量通过；局部规划补修须保持原清单、原序与稳定ID，只改报错字段，不能用空数组覆盖，辅助候选重编不应阻断有效绘制项。

1. 蓝/紫两个相同形状按钮：同家族不同variant，各自标签和底板不串色，不共用一个entity_id。
2. 一枚金币紧贴数字：两个语义槽位保留；不能把数字0认成10，也不能裁掉金币。
3. 多色字标带孔洞/微点：整体身份保留，真实颜色子路径完整；AA边缘不拆新物件，残字套组不算修复。
4. 人物坐在明确一体坐垫上、旁边有独立按钮：人物与坐垫按证据完整提取，按钮不合并；不以检测框相交作证明。
5. 底部浅色云形遮住背景：按真实边界判前景并从干净背景去件，不因色浅或面积大烘焙到底图。
6. 旋转两行英文带斜体：核对文案、基线和实际墨迹，逐行拟合，不用框高当字号或宽度拉伸。
7. 半透明且有蒙版的组：整体透明度和蒙版不丢；不能无损解组时拒绝，不为了叶层“更独立”改变画面。
8. 看似九宫格面板：记录可见角/边与内容槽位，未观察到的伸缩参数保留未知，不拆成九张图。
9. 隐藏旧版与当前修正版重叠：旧版不进当前实体候选；未选中节点和图片字节不变，修正成功保留旧版、可撤销；按2.36仅点击“保存工程”才持久保存。

外部技能筛选：已阅读[Anthropic frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md)，其原创/重设计目标不适合替换原图；已阅读[Vercel web-design-guidelines](https://github.com/vercel-labs/agent-skills/blob/main/skills/web-design-guidelines/SKILL.md)及其[检查规则](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md)，可用于工作台交互、可访问性与性能检查，不能作为语义拆层器。未盲目安装或引入风格美化。
