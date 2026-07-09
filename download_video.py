#!/usr/bin/env python3
"""
yt-dlp 视频下载工具

基于 yt-dlp 库的命令行视频下载工具，支持通过 URL 下载视频文件。
自动选择最高画质的视频和音频流，合并为 MP4 格式。

用法:
    python download_video.py <视频URL> [保存路径]

示例:
    python download_video.py https://www.youtube.com/watch?v=xxxx
    python download_video.py https://www.youtube.com/watch?v=xxxx ./my_videos
"""

import os
import sys
import argparse
from typing import Optional

try:
    import yt_dlp
except ImportError:
    print("错误: 缺少 yt-dlp 库，请运行: pip install yt-dlp")
    sys.exit(1)


def download_video(url: str, output_path: Optional[str] = None) -> str:
    """
    下载指定 URL 的视频文件。

    自动选择最高画质的视频+音频组合，合并为 MP4 格式。
    输出文件以视频标题命名。

    Args:
        url: 视频 URL（如 YouTube、B站等 yt-dlp 支持的平台）
        output_path: 保存路径（可选，默认为 ./downloads）

    Returns:
        下载完成的文件路径

    Raises:
        Exception: 下载过程中发生错误时抛出
    """
    if output_path is None:
        output_path = os.path.join(os.getcwd(), "downloads")

    # 确保输出目录存在
    os.makedirs(output_path, exist_ok=True)

    # 配置 yt-dlp 选项
    ydl_opts = {
        # 输出模板：视频标题 + 扩展名
        "outtmpl": os.path.join(output_path, "%(title)s.%(ext)s"),
        # 格式选择：最佳画质视频+最佳音频，合并为 mp4
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        # 自动合并视频和音频流
        "merge_output_format": "mp4",
        # 显示下载进度
        "progress_hooks": [_progress_hook],
        # 允许覆盖已存在的文件
        "overwrites": True,
        # 保留原始文件名（不截断）
        "restrictfilenames": False,
    }

    print(f"🎬 开始下载: {url}")
    print(f"📁 保存路径: {output_path}")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 提取视频信息并下载
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "unknown")
            ext = info.get("ext", "mp4")
            filename = f"{title}.{ext}"
            filepath = os.path.join(output_path, filename)

            print(f"\n✅ 下载完成: {filepath}")
            return filepath

    except Exception as e:
        print(f"\n❌ 下载失败: {e}")
        raise


def _progress_hook(d: dict) -> None:
    """
    下载进度回调函数，在控制台显示下载进度。

    Args:
        d: yt-dlp 进度字典
    """
    if d["status"] == "downloading":
        # 获取下载进度百分比
        percent = d.get("_percent_str", "N/A").strip()
        speed = d.get("_speed_str", "N/A").strip()
        eta = d.get("_eta_str", "N/A").strip()
        print(f"\r⏳ 下载中... {percent} | 速度: {speed} | 剩余: {eta}", end="", flush=True)
    elif d["status"] == "finished":
        print(f"\r✅ 下载完成，正在合并视频和音频...")


def main():
    """命令行入口函数"""
    parser = argparse.ArgumentParser(
        description="基于 yt-dlp 的视频下载工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s https://www.youtube.com/watch?v=xxxx
  %(prog)s https://www.youtube.com/watch?v=xxxx ./my_videos
  %(prog)s https://www.bilibili.com/video/BV1xx411c7mD
        """,
    )
    parser.add_argument("url", help="视频 URL（支持 YouTube、B站等平台）")
    parser.add_argument(
        "output_path",
        nargs="?",
        default=None,
        help="保存路径（可选，默认为 ./downloads）",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s 1.0.0 (yt-dlp {yt_dlp.version.__version__})",
    )

    args = parser.parse_args()

    try:
        download_video(args.url, args.output_path)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户取消下载")
        sys.exit(1)
    except Exception as e:
        print(f"\n错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
