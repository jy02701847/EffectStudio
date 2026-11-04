---
slug: effectstudio
name: EffectStudio 效果图洗图软件
displayName: EffectStudio 效果图洗图软件
description: 建筑/室内效果图自动洗图工具：智能分析直方图自动调色，Lab 亮度域处理不偏色不过曝，支持批量处理与神经网络降噪（可选）。Windows 绿色版，解压即用。
version: 1.1.0
summary: 效果图自动调色软件（Windows 绿色版），智能识图定参，不偏色不过曝，批量处理
license: MIT
tags:
  - 图像处理
  - 效果图
  - 调色
  - 建筑可视化
  - 桌面软件
---

# EffectStudio · 效果图洗图软件

针对**建筑效果图 / 室内渲染图**优化的本地洗图工具。拖图进窗口，自动分析直方图并套用影调与色彩方案，输出干净通透的成片——不偏色、不过曝、暗部不死黑。

## 它解决什么问题

渲染出的效果图常见三种毛病：整体发灰、白墙天花洗成一片死白、暗部糊成黑块。EffectStudio 每张图都**重新读图算参数**（不是固定滤镜），处理逻辑在 Lab 亮度域完成，只动亮度不染色，并有高光收口与中调锚定两道防护：

| 指标 | 效果 |
|---|---|
| 自动识图 | 每张图独立分析曝光/对比/色偏，无需手动调参 |
| 防过曝 | 高光段平滑压缩，白墙保留层次（实测 ≥250 死白像素 6.14% → 0%） |
| 防偏色 | Lab 亮度域处理，杜绝 RGB 逐通道导致的色染 |
| 批量 | 多图一次拖入，一键打包 ZIP 导出 |
| 神经网络降噪（可选） | 接入 NVIDIA NeuralScreen 运行时后可启用，未装自动跳过 |

## 获取与安装（部署即用）

**软件本体（约 70MB zip）从发布仓库下载**（见下方「下载地址」），安装三步：

1. 下载 `EffectStudio_v1.1.0_绿色版.zip`，解压到任意目录（如 `D:\EffectStudio`）
2. 双击 `EffectStudio.exe`，自动弹出操作窗口（原生程序窗口，非浏览器页面）
3. 拖图进窗口 → 点处理 → 完成后单张保存或批量导出 ZIP

无需安装、无需管理员权限、无后台驻留、图片全程不上传。

## 系统要求

- Windows 10/11（64 位）
- 纯调色：无显卡要求，1080p 约 2~3 秒，8K 约 20~35 秒
- 神经网络降噪：需 NVIDIA 显卡 + NeuralScreen 运行时（可选，未装不影响其他功能）

## 使用提示

- 默认「智能 Auto」自动定参；力度 / 质感 / 色温三个滑块可微调
- 处理结果默认保存在程序目录 `output` 文件夹
- 前后对比：在预览上按住拖动即可分屏查看

## 更新日志

- **v1.1.0**：原生程序窗口（pywebview/WebView2）；新增在线升级框架；程序图标；SkillHub 主页上线
- **v1.0.0**：Lab 影调引擎（防偏色/防过曝）；批量处理与 ZIP 导出；PyInstaller 绿色打包

## 下载地址

**GitHub Releases（官方发布页，长期有效）**：

- v1.1.0 绿色版直链：https://github.com/jy02701847/EffectStudio/releases/download/v1.1.0/EffectStudio_v1.1.0.zip
- 发布页（含历史版本与更新日志）：https://github.com/jy02701847/EffectStudio/releases
- 源码仓库：https://github.com/jy02701847/EffectStudio

软件遵循 MIT 协议开源。新版本发布后会同步更新本页与 Release 附件。
