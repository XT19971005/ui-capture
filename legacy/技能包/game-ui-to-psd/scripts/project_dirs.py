from pathlib import Path
def project_dirs(project):
    if Path(project).name=='1_过程':
        return dict(input='../2_输出',assets='01_素材',plan='02_结构',output='../2_输出',qa='03_检查',compact=True)
    return dict(input='01_输入',assets='02_素材',plan='03_结构',output='04_输出',qa='05_检查',compact=False)
