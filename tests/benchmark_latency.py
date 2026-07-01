#!/usr/bin/env python3
"""Latency benchmark for StoryTeller API — measures TTFB and total time for each feature.

Usage: python3 tests/benchmark_latency.py [sonnet|grok]
"""

import json
import os
import sys
import time
import requests

API_BASE = os.environ.get("API_BASE", "https://akfvsew3we.execute-api.us-west-2.amazonaws.com/prod")
EMAIL = "e2e-test@storyteller.dev"


def get_token():
    path = "/tmp/storyteller-dev-token.txt"
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    # Generate token
    import boto3
    client = boto3.client('cognito-idp', region_name='us-west-2')
    resp = client.initiate_auth(
        ClientId='1juc236qmkme87ohqibblca68b',
        AuthFlow='USER_PASSWORD_AUTH',
        AuthParameters={
            'USERNAME': EMAIL,
            'PASSWORD': 'Test6e6b80e86e571fb1!1'
        }
    )
    token = resp['AuthenticationResult']['IdToken']
    with open(path, 'w') as f:
        f.write(token)
    return token


def stream_chat(message: str, session_id: str, token: str, timeout: int = 120) -> dict:
    """Send a chat message and measure latency."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "email": EMAIL,
        "message": message,
        "session_id": session_id,
        "file_refs": [],
    }

    t_start = time.time()
    ttfb = None
    full_text = ""
    keepalives = 0
    chunks = 0

    try:
        resp = requests.post(
            f"{API_BASE}/chat-stream",
            json=payload,
            headers=headers,
            stream=True,
            timeout=timeout,
        )

        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:300]}",
                    "latency_ms": int((time.time() - t_start) * 1000)}

        for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
            if not chunk:
                continue
            if "__KEEPALIVE__" in chunk:
                keepalives += 1
                chunk = chunk.replace("__KEEPALIVE__", "")
                continue
            if chunk.strip() and ttfb is None:
                ttfb = time.time() - t_start
            chunks += 1
            full_text += chunk

        t_total = time.time() - t_start

        return {
            "text": full_text.strip(),
            "ttfb_ms": int(ttfb * 1000) if ttfb else None,
            "total_ms": int(t_total * 1000),
            "keepalives": keepalives,
            "chunks": chunks,
            "length": len(full_text.strip()),
        }

    except requests.exceptions.Timeout:
        return {"error": "Timeout", "total_ms": int((time.time() - t_start) * 1000)}
    except Exception as e:
        return {"error": str(e), "total_ms": int((time.time() - t_start) * 1000)}


def run_benchmark(label: str = ""):
    token = get_token()
    results = []

    tests = [
        ("Greeting", "שלום! מה שלומך?", 30),
        ("Session naming", "בוא נתכנן סרטון על Kubernetes", 60),
        ("Deep research", "תחקור את הנושא AWS Lambda SnapStart - מה זה ומתי משתמשים", 120),
        ("QR code", "תייצר QR code ל https://aws.amazon.com", 60),
        ("Content generation", "תכתוב לי hook חזק ל-30 שניות ראשונות של סרטון על Docker", 60),
    ]

    print(f"\n{'='*70}")
    print(f"  LATENCY BENCHMARK — {label or 'StoryTeller Dev'}")
    print(f"  API: {API_BASE}")
    print(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print(f"{'='*70}\n")
    print(f"{'Test':<25} {'TTFB':>8} {'Total':>8} {'Chars':>7} {'Status'}")
    print(f"{'-'*25} {'-'*8} {'-'*8} {'-'*7} {'-'*10}")

    for name, message, timeout in tests:
        sid = f"bench-{name.replace(' ', '-').lower()}-{int(time.time())}"
        result = stream_chat(message, sid, token, timeout=timeout)

        if "error" in result:
            status = f"❌ {result['error'][:30]}"
            ttfb_str = "-"
            total_str = f"{result.get('total_ms', '?')}ms"
            chars = 0
        else:
            status = "✅"
            ttfb_str = f"{result['ttfb_ms']}ms" if result['ttfb_ms'] else "-"
            total_str = f"{result['total_ms']}ms"
            chars = result['length']

        print(f"{name:<25} {ttfb_str:>8} {total_str:>8} {chars:>7} {status}")
        results.append({
            "name": name,
            "ttfb_ms": result.get("ttfb_ms"),
            "total_ms": result.get("total_ms"),
            "length": result.get("length", 0),
            "error": result.get("error"),
        })

        # Small delay between tests
        time.sleep(1)

    # Summary
    print(f"\n{'='*70}")
    successful = [r for r in results if not r.get("error")]
    if successful:
        avg_ttfb = sum(r["ttfb_ms"] for r in successful if r["ttfb_ms"]) / max(1, len([r for r in successful if r["ttfb_ms"]]))
        avg_total = sum(r["total_ms"] for r in successful) / len(successful)
        print(f"  Avg TTFB:  {avg_ttfb:.0f}ms")
        print(f"  Avg Total: {avg_total:.0f}ms")
        print(f"  Passed: {len(successful)}/{len(results)}")
    print(f"{'='*70}\n")

    return results


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else ""
    run_benchmark(label)
