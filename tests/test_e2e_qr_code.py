#!/usr/bin/env python3
"""StoryTeller E2E Test — QR Code Generation via live API."""
import time
import requests

API_BASE = "https://c1p7y5p1di.execute-api.us-east-1.amazonaws.com/prod"
EMAIL = "g1@amazon.com"


def get_token():
    with open("/tmp/storyteller-test-token.txt") as f:
        return f.read().strip()


def stream_chat(message: str, session_id: str, token: str) -> dict:
    """Send a chat message and collect the streamed response."""
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

    try:
        resp = requests.post(
            f"{API_BASE}/chat-stream",
            json=payload,
            headers=headers,
            stream=True,
            timeout=120,
        )

        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:500]}"}

        full_text = ""
        for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
            if not chunk:
                continue
            cleaned = chunk.replace("__KEEPALIVE__", "")
            full_text += cleaned

        return {"text": full_text.strip(), "length": len(full_text.strip())}

    except requests.exceptions.Timeout:
        return {"error": "Request timed out (120s)"}
    except Exception as e:
        return {"error": str(e)}


def test_qr_code_generation():
    """Test: ask agent to generate a QR code for a valid URL."""
    token = get_token()
    sid = f"test-qr-{int(time.time())}"

    print("\n" + "=" * 60)
    print("E2E TEST: QR Code Generation")
    print("=" * 60)

    message = "Generate a QR code for https://aws.amazon.com"
    print(f"Message: {message}")

    t0 = time.time()
    result = stream_chat(message, sid, token)
    elapsed = time.time() - t0
    print(f"Response time: {elapsed:.1f}s")

    if "error" in result:
        print(f"❌ FAILED: {result['error']}")
        return False

    text = result["text"]
    print(f"Response length: {len(text)} chars")
    print(f"Response preview: {text[:300]}...")

    # Verify media:// reference is present
    if "media://" not in text:
        print("❌ FAILED: Response does not contain media:// reference")
        print(f"Full response: {text}")
        return False
    print("✅ Contains media:// reference")

    # Extract file_id from media:// reference
    import re
    media_match = re.search(r"media://([^\s\)]+)", text)
    if not media_match:
        print("❌ FAILED: Could not extract file_id from media:// ref")
        return False

    file_id = media_match.group(1)
    print(f"✅ Extracted file_id: {file_id}")

    # Verify the file can be resolved via the download endpoint
    headers = {
        "Authorization": f"Bearer {token}",
    }
    download_resp = requests.get(
        f"{API_BASE}/sessions/{sid}/files/{file_id}",
        headers=headers,
    )

    if download_resp.status_code != 200:
        print(f"❌ FAILED: File download endpoint returned {download_resp.status_code}")
        print(f"Body: {download_resp.text[:200]}")
        return False

    download_data = download_resp.json()
    download_url = download_data.get("download_url", "")
    if not download_url:
        print("❌ FAILED: No download_url in response")
        return False
    print(f"✅ Got presigned URL: {download_url[:80]}...")

    # Verify the presigned URL returns a valid PNG
    png_resp = requests.get(download_url, timeout=10)
    if png_resp.status_code != 200:
        print(f"❌ FAILED: Presigned URL returned {png_resp.status_code}")
        return False

    content_type = png_resp.headers.get("content-type", "")
    if "image/png" not in content_type and not png_resp.content[:4] == b"\x89PNG":
        print(f"❌ FAILED: Response is not a PNG (content-type: {content_type})")
        return False

    print(f"✅ Valid PNG ({len(png_resp.content)} bytes)")
    print("\n✅ ALL QR CODE E2E CHECKS PASSED")
    return True


if __name__ == "__main__":
    import sys
    success = test_qr_code_generation()
    sys.exit(0 if success else 1)
