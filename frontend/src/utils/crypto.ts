/**
 * 客户端密码 SHA-256 哈希，避免明文密码在 HTTP 传输中暴露。
 * 注意：这不能替代 HTTPS，只是 defense-in-depth —— 攻击者截获 hash 后仍可重放。
 */
export async function hashPassword(password: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(password);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
