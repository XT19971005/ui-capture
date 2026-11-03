# AI拆图助手便携分享包

本目录保留AI拆图助手自己的打包器和离线回归。打包器从工作区根目录读取同级的 `AI拆图助手`、`技能包`，仅收录运行程序及必要依赖，并在替换 ZIP 前校验 CRC。

在工作区根目录执行：

```powershell
& 'AI拆图助手/依赖/运行环境/python/python.exe' 'AI拆图助手/开发源码/分享打包/build_shijie_share.py' --out '分享包/AI拆图助手_便携分享版.zip'
& 'AI拆图助手/依赖/运行环境/python/python.exe' 'AI拆图助手/开发源码/分享打包/test_shijie_share.py'
& 'AI拆图助手/依赖/运行环境/python/python.exe' 'AI拆图助手/开发源码/分享打包/test_portable_relocation.py'
& 'AI拆图助手/开发源码/分享打包/test_portable_launcher.ps1'
```

搬迁验收仅在临时目录解压检查，结果直接在聊天说明；无论成功或失败都清理解压副本，不创建测试结果交付目录。日常入口为 AI拆图助手/打开AI拆图助手.exe；维护启动脚本位于 开发源码/启动维护。
