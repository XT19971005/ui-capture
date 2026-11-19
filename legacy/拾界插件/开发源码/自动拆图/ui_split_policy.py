"""Game UI splitting decisions; analysis only, no generation side effects."""
DECISION_FIELDS={'splitReason':('拆分原因',200),'keepTogether':('保留整体',200),'separateParts':('另拆对象',200),'uncertainty':('待确认',200)}
RULES=(
 '游戏UI拆分以独立编辑、状态变化与复用职责为依据，不以颜色块数或层数为目标。逐对象解释拆什么、不另拆什么、为什么；未说明不能写成已理解完整。'
 '面板和按钮底板与普通标题、文案、数值分别拆，但同属一个控件的底板、文字、图标用相同语义组关联；按钮内金边、铆钉、花纹、内在高光一般随底板保留整体，不机械拆碎。'
 '普通连续文字按完整句或字段保留可编辑文字，不逐字拆；复杂材质艺术字保留整块图片，不能冒充可编辑普通字。简单纯色或可准确还原的形状用矢量；金属、宝石、复杂纹理和立体光照图标按完整图片。'
 '复选框、单选项、进度条、滑块、页签等可变部件按职责分开；每个当前实际可见位置独立标注，同款仅在造型材质状态一致有证据时复用。不要凭静态图虚构按下状态、动画帧、下一页或隐藏弹窗。'
 '背景中未见独立编辑或运动依据的云、山、水和装饰可以整体保留；有明确独立动画或用户指定才细拆。没有另拆项就明确写无需另拆，不将无关未圈对象加入手动方案。'
 '每个对象需说明拆分原因、保留整体的部件与原因、另拆对象及归属、待确认疑点。观察到的事实和推测分开；看不清或被遮挡明确待确认，不能靠补一句没有疑点宣称已核对。'
)
def decision_note(item,note):
 lines=[]
 for key,(label,limit) in DECISION_FIELDS.items():
  if key not in item:continue
  value=item[key]
  if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 and c not in '\n\t' for c in value):raise ValueError('拆分与保留说明无效')
  lines.append(label+'：'+(value.strip() or '尚未说明，需核对'))
 if not lines:return note
 if note:lines.append('样式与范围：'+note)
 full='\n'.join(lines)
 if len(full)>1000:raise ValueError('拆分与保留说明超过1000字，请精简后核对')
 return full
