#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests>=2.31"]
# ///
"""RustFS / MinIO 大桶一键清空：发 `DELETE /<bucket>` 带非标准 header
`x-minio-force-delete: true`，让 server 端内部清掉所有 version + delete marker
+ 桶元数据，绕过 client 列举（大 versioning 桶上 `mc rb --force` 的 ListObjectVersions
会 hang，这是唯一跑得通的路径）。

boto3 不支持注入这个 header，所以这里手拼 sigv4 签名直接打 RustFS HTTP。

server 端是异步 job：请求发出后 client 断开也不影响 server 继续清（百万级对象可能跑数
小时）。默认 **发完即返回、不等 server 跑完**；过几小时用 `mc ls <alias>/` 看桶是否消失。

示例：
    uv run rustfs_force_delete_bucket.py \\
        --endpoint http://rustfs:9000 --bucket my-big-bucket \\
        --access-key AK --secret-key SK
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import hmac

import requests


def sigv4_force_delete_bucket(endpoint: str, ak: str, sk: str, bucket: str,
                              region: str = "us-east-1", timeout: int = 60):
    """对 RustFS/MinIO 发 DELETE /<bucket>，带 x-minio-force-delete:true。"""
    headers = {"x-minio-force-delete": "true"}
    t = datetime.datetime.now(datetime.UTC)
    amz_date = t.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = t.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(b"").hexdigest()

    headers["host"] = endpoint.split("//")[-1]
    headers["x-amz-content-sha256"] = payload_hash
    headers["x-amz-date"] = amz_date

    sorted_h = sorted(headers.items())
    canonical_headers = "".join(f"{k}:{v}\n" for k, v in sorted_h)
    signed_headers = ";".join(k for k, _ in sorted_h)
    canonical_request = (
        f"DELETE\n/{bucket}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )
    cred_scope = f"{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amz_date}\n{cred_scope}\n"
        f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
    )

    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k_date = _hmac(f"AWS4{sk}".encode(), date_stamp)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, "s3")
    k_signing = _hmac(k_service, "aws4_request")
    sig = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
    headers["Authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={ak}/{cred_scope}, "
        f"SignedHeaders={signed_headers}, Signature={sig}"
    )

    sess = requests.Session()
    sess.trust_env = False  # 跳过 OS 代理 env（如 Mihomo/Clash 的 http_proxy）
    return sess.delete(f"{endpoint}/{bucket}", headers=headers, timeout=timeout, proxies={})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--endpoint", required=True, help="如 http://rustfs:9000")
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--access-key", required=True)
    ap.add_argument("--secret-key", required=True)
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--timeout", type=int, default=60,
                    help="client read timeout(s)；超时不代表 server 失败，server 会继续清")
    ap.add_argument("--wait", action="store_true",
                    help="等 server 跑完再返回（默认不等，发完即走）")
    args = ap.parse_args()

    timeout = args.timeout if args.wait else min(args.timeout, 10)
    try:
        resp = sigv4_force_delete_bucket(args.endpoint, args.access_key, args.secret_key,
                                         args.bucket, args.region, timeout=timeout)
        print(f"HTTP {resp.status_code}: {resp.text[:300]}")
    except requests.Timeout:
        print("client 超时——这是预期的：server 端异步清理仍在继续。"
              "\n过几小时用 `mc ls <alias>/` 看桶是否消失。")


if __name__ == "__main__":
    main()
