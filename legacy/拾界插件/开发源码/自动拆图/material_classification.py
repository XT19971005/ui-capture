"""Material evidence checks independent of long-lived native-plan modules."""
import re

def material_icon(name, note=''):
 text=str(name)+'；'+str(note)
 if re.search(r'底板|数量|文字|纯色|扁平|剪影|线性',str(name)):return False
 return bool(re.search(r'代币|金币|货币|晶体|宝石|徽章|勋章|图标',str(name)) and
  (re.search(r'金属|折射|浮雕|复杂立体|立体材质|镶嵌',text) or
   re.search(r'金[色边]',text) and re.search(r'紫蓝|晶体|宝石',text)))

STRICT_CLASSIFICATION_RULES='严格按原图视觉证据分类：图标是用途而非矢量类型。货币、徽章、宝石等带金属边、浮雕、折射和复杂立体光照时，完整主体必须image；例如金边紫蓝圆币及其星形内纹整体提取透明图片，不能用圆环、渐变圆和几块浅色碎片冒充。只有真正平面纯色或少量可准确还原形状才vector。标注ellipse/rect/envelope只表示定位圈形，绝不是生成图层类型。模糊看不清标auto并说明，不按名称猜矢量。逐项核对完整范围、细部、类别、同款姿态和层序，内部材质纹样不拆独立控件。分类与材质证据冲突时停止该对象，明确纠正分类，不自动付费。'
