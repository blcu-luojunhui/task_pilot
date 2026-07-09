/**
 * 客户端密码 SHA-256 哈希。
 * 优先使用 Web Crypto API（secure context），不可用时降级为明文发送。
 * 这只是 defense-in-depth，真正的安全依赖 HTTPS。
 */
export async function hashPassword(password: string): Promise<string> {
  if (!crypto.subtle) {
    console.warn('Web Crypto API 不可用，密码将以明文传输。建议使用 HTTPS。');
    return password;
  }
  const encoder = new TextEncoder();
  const data = encoder.encode(password);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
