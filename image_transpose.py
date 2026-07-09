#!/usr/bin/env python3
"""
图片转置工具 - 将图片的宽高互换（转置）

转置操作相当于：
  1. 将图片顺时针旋转 90 度
  2. 再水平翻转（镜像）

即：新图片的像素 (x, y) = 原图片的像素 (y, x)

依赖：pip install Pillow
"""

import os
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("错误：需要安装 Pillow 库，请运行: pip install Pillow")
    sys.exit(1)


def transpose_image(input_path: str, output_path: str | None = None) -> str:
    """
    对图片进行转置操作（交换宽高）

    Args:
        input_path:  输入图片路径
        output_path: 输出图片路径（None 则自动生成）

    Returns:
        输出图片的路径
    """
    # 打开图片
    img = Image.open(input_path)
    print(f"  原图尺寸: {img.width} x {img.height} (宽 x 高)")
    print(f"  图片格式: {img.format}")
    print(f"  颜色模式: {img.mode}")

    # 执行转置：TRANSPOSE = 旋转90度 + 水平翻转
    transposed = img.transpose(Image.TRANSPOSE)
    print(f"  转置后尺寸: {transposed.width} x {transposed.height} (宽 x 高)")

    # 确定输出路径
    if output_path is None:
        in_path = Path(input_path)
        output_path = str(in_path.parent / f"{in_path.stem}_transposed{in_path.suffix}")

    # 保存
    transposed.save(output_path)
    print(f"  已保存到: {output_path}")

    return output_path


def main():
    # --- 使用示例 ---
    # 方式1：命令行参数
    if len(sys.argv) >= 2:
        input_path = sys.argv[1]
        output_path = sys.argv[2] if len(sys.argv) >= 3 else None

        if not os.path.isfile(input_path):
            print(f"错误：文件不存在 - {input_path}")
            sys.exit(1)

        print(f"开始转置图片: {input_path}")
        transpose_image(input_path, output_path)
        print("完成！")
        return

    # 方式2：交互式输入
    print("=" * 50)
    print("  图片转置工具")
    print("=" * 50)

    while True:
        input_path = input("\n请输入图片路径（输入 q 退出）: ").strip()
        if input_path.lower() in ("q", "quit", "exit"):
            print("退出。")
            break

        if not os.path.isfile(input_path):
            print(f"错误：文件不存在 - {input_path}")
            continue

        output_path = input("请输入输出路径（留空自动生成）: ").strip() or None

        try:
            transpose_image(input_path, output_path)
            print("完成！")
        except Exception as e:
            print(f"处理失败: {e}")

        again = input("\n是否继续处理其他图片？(y/n): ").strip().lower()
        if again != "y":
            print("退出。")
            break


if __name__ == "__main__":
    main()
