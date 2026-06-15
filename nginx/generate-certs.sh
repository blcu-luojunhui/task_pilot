#!/usr/bin/env bash
# 生成自签名 SSL 证书（适用于没有域名的场景）
# 浏览器会提示"不安全"，但通信加密正常。
# 如果后续有了域名，替换为 Let's Encrypt 证书即可。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CERTS_DIR="${SCRIPT_DIR}/certs"

mkdir -p "$CERTS_DIR"

CERT_FILE="${CERTS_DIR}/server.crt"
KEY_FILE="${CERTS_DIR}/server.key"
DHPARAM_FILE="${CERTS_DIR}/dhparam.pem"

# ── 自签名证书 ──────────────────────────────────────────
if [[ -f "$CERT_FILE" && -f "$KEY_FILE" ]]; then
    echo "[skip] 证书已存在: $CERT_FILE"
else
    echo "[gen] 生成自签名证书 (3650 天有效)..."
    openssl req -x509 -newkey rsa:2048 -days 3650 -nodes \
        -keyout "$KEY_FILE" \
        -out "$CERT_FILE" \
        -subj "/C=CN/ST=Beijing/L=Beijing/O=TaskPilot/CN=taskpilot" \
        -addext "subjectAltName=IP:127.0.0.1"
    echo "[ok] 证书生成完成"
fi

# ── DH 参数（非必须但提升安全性） ──────────────────────
if [[ -f "$DHPARAM_FILE" ]]; then
    echo "[skip] DH 参数已存在"
else
    echo "[gen] 生成 DH 参数 (2048-bit，约 10-30 秒)..."
    openssl dhparam -out "$DHPARAM_FILE" 2048
    echo "[ok] DH 参数生成完成"
fi

echo ""
echo "=== 证书信息 ==="
openssl x509 -in "$CERT_FILE" -text -noout | grep -E "Subject:|Not Before|Not After|DNS|IP"
echo ""
echo "证书路径: $CERTS_DIR"
echo "docker-compose up 前确保此目录存在。"
