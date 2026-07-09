/** 上传前压缩大图，避免超过 512KB 限制 */
export async function prepareAvatarFile(file: File, maxBytes = 512 * 1024): Promise<File> {
  if (file.size <= maxBytes) return file;
  if (!file.type.startsWith('image/')) {
    throw new Error('仅支持图片文件');
  }

  const bitmap = await createImageBitmap(file);
  const maxSide = 256;
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));

  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    bitmap.close();
    throw new Error('无法处理图片');
  }
  ctx.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();

  for (const quality of [0.88, 0.75, 0.6]) {
    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, 'image/jpeg', quality);
    });
    if (blob && blob.size <= maxBytes) {
      return new File([blob], file.name.replace(/\.\w+$/, '.jpg'), { type: 'image/jpeg' });
    }
  }

  throw new Error('图片过大，请选择更小的文件');
}

/** 构建头像图片 URL（img 标签无法带 Authorization，使用 token 查询参数） */
export function buildAvatarImageUrl(
  role: 'user' | 'agent',
  token: string | null | undefined,
  versionKey: string | null | undefined,
): string | null {
  if (!token || !versionKey) return null;
  const params = new URLSearchParams({
    role,
    token,
    v: versionKey,
  });
  return `/api/auth/avatar/image?${params.toString()}`;
}
