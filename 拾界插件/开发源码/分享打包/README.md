# 拾界便携分享包

本目录保留拾界插件自己的打包器和离线回归。打包器从工作区根目录读取同级的 `拾界插件`、`技能包`，仅收录运行程序及必要依赖，并在替换 ZIP 前校验 CRC。

在工作区根目录执行：

```powershell
& '拾界插件/依赖/运行环境/python/python.exe' '拾界插件/开发源码/分享打包/build_shijie_share.py' --out '分享包/拾界_便携分享版.zip'
& '拾界插件/依赖/运行环境/python/python.exe' '拾界插件/开发源码/分享打包/test_shijie_share.py'
& '拾界插件/依赖/运行环境/python/python.exe' '拾界插件/开发源码/分享打包/test_portable_relocation.py'
& '拾界插件/开发源码/分享打包/test_portable_launcher.ps1'
```

真实解压搬迁验收使用对应任务目录中的 `validate_portable_share.py`；其结果写入该目录，不进入分享包。
