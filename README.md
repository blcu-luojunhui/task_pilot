# yt-dlp 视频下载工具

基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 库的命令行视频下载工具，支持通过 URL 下载视频文件。

## 功能特性

- ✅ 通过 URL 下载视频（支持 YouTube、B站、抖音等 yt-dlp 支持的平台）
- ✅ 自动选择最高画质的视频和音频流
- ✅ 自动合并视频和音频为 MP4 格式
- ✅ 输出文件以视频标题命名
- ✅ 支持自定义保存路径
- ✅ 显示下载进度和状态信息

## 环境要求

- Python 3.6 或更高版本
- 网络连接

## 安装

```bash
# 1. 安装依赖
pip install yt-dlp

# 2. 下载脚本
# 直接使用本仓库中的 download_video.py 即可
```

## 使用方法

### 基本用法

下载视频到默认目录 `./downloads`：

```bash
python download_video.py https://www.youtube.com/watch?v=xxxx
```

### 指定保存路径

```bash
python download_video.py https://www.youtube.com/watch?v=xxxx ./my_videos
```

### 在 Python 代码中调用

```python
from download_video import download_video

# 下载到默认路径
filepath = download_video("https://www.youtube.com/watch?v=xxxx")

# 下载到指定路径
filepath = download_video("https://www.youtube.com/watch?v=xxxx", "./my_videos")

print(f"视频已保存到: {filepath}")
```

## 支持的平台

yt-dlp 支持数百个视频平台，包括但不限于：

- YouTube
- Bilibili（B站）
- 抖音 / TikTok
- Twitter / X
- Instagram
- Facebook
- 更多请参考 [yt-dlp 支持站点列表](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)

## 注意事项

- 请遵守各视频平台的服务条款
- 下载受版权保护的内容可能违反当地法律
- 请仅下载您有权下载的内容

## 项目结构

```
.
├── download_video.py   # 主脚本（核心下载功能 + 命令行入口）
├── requirements.txt    # Python 依赖
└── README.md          # 本文件
```
