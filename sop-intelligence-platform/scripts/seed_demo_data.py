"""Demo 种子数据初始化脚本 — 验证后端 Demo 路由可用性。

用法::

    python scripts/seed_demo_data.py

无需 PostgreSQL / MinIO，仅调用 Demo 种子端点验证返回 200。
"""

from __future__ import annotations

import sys

import httpx

BASE_URL = "http://localhost:8000"

ENDPOINTS = [
    ("GET", "/api/sop/demo", "SOP Demo 种子"),
    ("GET", "/api/fsm/demo", "FSM Demo 种子"),
]


def main() -> int:
    ok = True
    client = httpx.Client(timeout=10.0)

    for method, path, label in ENDPOINTS:
        url = f"{BASE_URL}{path}"
        try:
            resp = client.request(method, url)
            if resp.status_code == 200:
                print(f"  ✅ {label}: {url} → {resp.status_code}")
            else:
                print(f"  ❌ {label}: {url} → {resp.status_code}")
                ok = False
        except httpx.ConnectError:
            print(f"  ❌ {label}: 无法连接 {url}（后端是否已启动？）")
            ok = False

    # 验证反馈端点
    try:
        resp = client.post(
            f"{BASE_URL}/api/feedback/false-positive",
            json={
                "event_id": "test-evt-001",
                "workstation_id": "ws-demo-01",
                "operator_comment": "种子数据测试",
            },
        )
        if resp.status_code == 202:
            print(f"  ✅ 误报反馈: /api/feedback/false-positive → {resp.status_code}")
        else:
            print(f"  ❌ 误报反馈: /api/feedback/false-positive → {resp.status_code}")
            ok = False
    except httpx.ConnectError:
        print("  ❌ 误报反馈: 无法连接（后端是否已启动？）")
        ok = False

    client.close()

    print()
    if ok:
        print("✅ 所有 Demo 端点验证通过")
        return 0
    print("❌ 部分端点异常，请检查后端日志")
    return 1


if __name__ == "__main__":
    sys.exit(main())
