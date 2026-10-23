"""
生成饺子 App 的签名密钥（PKCS12 格式），不需要安装 JDK / keytool。

用法（在 D:\\chatbot-ai 目录）：
    python android/make_keystore.py

会在你的用户目录下生成 jiaozi-keystore 文件夹，里面有：
    jiaozi-release.p12   签名密钥文件 —— 一定要备份，丢了以后就无法发布更新
    github-secrets.txt   要填到 GitHub Secrets 的 3 个值

⚠️ 这个文件夹不要放进项目目录、不要提交到 Git。
"""
import base64
import datetime
import os
import secrets
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

ALIAS = "jiaozi"
OUT_DIR = os.path.join(os.path.expanduser("~"), "jiaozi-keystore")
KEYSTORE = os.path.join(OUT_DIR, "jiaozi-release.p12")
SECRETS_TXT = os.path.join(OUT_DIR, "github-secrets.txt")


def main():
    if os.path.exists(KEYSTORE):
        sys.exit(f"已经存在 {KEYSTORE}，为了防止覆盖旧密钥，已停止。\n"
                 "签名密钥只能有一个，旧的丢了才需要重新生成。")
    os.makedirs(OUT_DIR, exist_ok=True)

    password = secrets.token_urlsafe(24)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Jiaozi"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "dumplings.photoidmaker.xyz"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365 * 30))   # 有效期 30 年
        .sign(key, hashes.SHA256())
    )
    data = pkcs12.serialize_key_and_certificates(
        name=ALIAS.encode(),
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode()),
    )
    with open(KEYSTORE, "wb") as f:
        f.write(data)

    with open(SECRETS_TXT, "w", encoding="utf-8") as f:
        f.write("把下面 3 项分别添加到 GitHub 仓库：Settings → Secrets and variables → Actions → New repository secret\n\n")
        f.write(f"Name: KEYSTORE_BASE64\nSecret:\n{base64.b64encode(data).decode()}\n\n")
        f.write(f"Name: KEYSTORE_PASSWORD\nSecret:\n{password}\n\n")
        f.write(f"Name: KEY_ALIAS\nSecret:\n{ALIAS}\n")

    print("[完成] 签名密钥已生成")
    print(f"   密钥文件：{KEYSTORE}")
    print(f"   GitHub Secrets 内容：{SECRETS_TXT}")
    print()
    print("下一步：打开 github-secrets.txt，把 3 项添加到 GitHub Secrets。")
    print("[重要] 把整个 jiaozi-keystore 文件夹备份到安全的地方（网盘/U 盘），丢了就无法再发布更新。")


if __name__ == "__main__":
    main()
