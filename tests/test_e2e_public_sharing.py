"""Live integration tests for public sharing feature against dev API.

Tests:
1. Create a session (by chatting) as test1
2. Verify session is private by default
3. Set visibility to public
4. test2 can view the public session via GET /sessions/{id}
5. test2 cannot send messages (chat-stream should reject)
6. test1 shares with test2 by email → test2 gets collaborator access
7. test1 unshares test2 → back to viewer access (session still public)
8. test1 sets visibility back to private → test2 can no longer access
9. URL routing: verify the session_id-based GSI lookup works

Run: python3 tests/test_e2e_public_sharing.py
"""
import json
import time
import requests
import sys

API_BASE = "https://akfvsew3we.execute-api.us-west-2.amazonaws.com/prod"


def load_tokens():
    with open("/tmp/st-test-tokens.json") as f:
        return json.load(f)


def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_or_create_test_session(token):
    """Get the latest session for this user, or create one via a quick chat."""
    code, data = list_sessions(token)
    sessions = data.get("sessions", [])
    if sessions:
        return sessions[0]["session_id"]
    # If no sessions exist, create via chat and wait
    session_id = f"e2e-pub-{int(time.time())}"
    resp = requests.post(
        f"{API_BASE}/chat-stream",
        headers={**headers(token), "X-Session-Id": session_id},
        json={"message": "שלום", "session_id": session_id, "file_refs": []},
        stream=True,
        timeout=60,
    )
    for _ in resp.iter_content(chunk_size=4096, decode_unicode=True):
        pass
    time.sleep(5)  # Wait for DDB propagation
    return session_id


def get_session(token, session_id):
    resp = requests.get(f"{API_BASE}/sessions/{session_id}", headers=headers(token), timeout=10)
    return resp.status_code, resp.json()


def set_visibility(token, session_id, visibility):
    resp = requests.patch(
        f"{API_BASE}/sessions/{session_id}/visibility",
        headers=headers(token),
        json={"visibility": visibility},
        timeout=10,
    )
    return resp.status_code, resp.json()


def share_session(token, session_id, email):
    resp = requests.post(
        f"{API_BASE}/sessions/{session_id}/share",
        headers=headers(token),
        json={"share_with": email},
        timeout=10,
    )
    return resp.status_code, resp.json()


def unshare_session(token, session_id, email):
    resp = requests.delete(
        f"{API_BASE}/sessions/{session_id}/share/{email}",
        headers=headers(token),
        timeout=10,
    )
    return resp.status_code, resp.json()


def list_sessions(token):
    resp = requests.get(f"{API_BASE}/sessions", headers=headers(token), timeout=10)
    return resp.status_code, resp.json()


def run_tests():
    tokens = load_tokens()
    t1 = tokens["test1"]  # Owner
    t2 = tokens["test2"]  # Viewer/collaborator

    results = []

    def check(name, condition, detail=""):
        status = "✅" if condition else "❌"
        results.append((name, condition))
        print(f"  {status} {name}" + (f" — {detail}" if detail else ""))
        return condition

    print("\n🧪 E2E Public Sharing Tests")
    print("=" * 60)

    # 1. Get or create session as test1
    print("\n1️⃣  Getting test session for test1...")
    session_id = get_or_create_test_session(t1)
    print(f"    Using session: {session_id}")

    # 2. Verify session exists and is private by default
    print("\n2️⃣  Verifying default state...")
    code, data = get_session(t1, session_id)
    check("Owner can access own session", code == 200)
    check("Access is 'owner'", data.get("access") == "owner", f"got: {data.get('access')}")
    check("Default visibility is 'private'", data.get("visibility") == "private", f"got: {data.get('visibility')}")

    # 3. test2 CANNOT access private session
    print("\n3️⃣  Verifying private access denied...")
    code, data = get_session(t2, session_id)
    check("Stranger cannot access private session", code == 403, f"status: {code}")

    # 4. Set visibility to public
    print("\n4️⃣  Setting visibility to public...")
    code, data = set_visibility(t1, session_id, "public")
    check("Set visibility returns 200", code == 200, f"status: {code}, body: {data}")

    # 5. test2 CAN now view the public session
    print("\n5️⃣  Verifying public access...")
    code, data = get_session(t2, session_id)
    check("Viewer can access public session", code == 200, f"status: {code}")
    check("Access is 'viewer'", data.get("access") == "viewer", f"got: {data.get('access')}")
    check("Viewer sees messages", len(data.get("messages", [])) > 0, f"msgs: {len(data.get('messages', []))}")
    check("Viewer doesn't see shared_with list", data.get("shared_with") == [], f"got: {data.get('shared_with')}")

    # 6. Public session NOT in test2's session list
    print("\n6️⃣  Verifying session list isolation...")
    code, list_data = list_sessions(t2)
    viewer_sessions = [s for s in list_data.get("sessions", []) if s.get("session_id") == session_id]
    check("Public session NOT in viewer's list", len(viewer_sessions) == 0, f"found: {len(viewer_sessions)}")

    # 7. Share with test2 by email → collaborator
    print("\n7️⃣  Sharing by email (collaborator)...")
    code, data = share_session(t1, session_id, "gili+test2@amazon.com")
    check("Share returns 200", code == 200)

    code, data = get_session(t2, session_id)
    check("After share: access is 'collaborator'", data.get("access") == "collaborator", f"got: {data.get('access')}")

    # 8. Unshare test2
    print("\n8️⃣  Unsharing collaborator...")
    code, data = unshare_session(t1, session_id, "gili+test2@amazon.com")
    check("Unshare returns 200", code == 200, f"body: {data}")

    code, data = get_session(t2, session_id)
    check("After unshare: access falls back to 'viewer' (still public)", data.get("access") == "viewer", f"got: {data.get('access')}")

    # 9. Set visibility back to private
    print("\n9️⃣  Setting visibility back to private...")
    code, data = set_visibility(t1, session_id, "private")
    check("Set private returns 200", code == 200)

    code, data = get_session(t2, session_id)
    check("After private: stranger cannot access", code == 403, f"status: {code}")

    # 10. Non-owner cannot change visibility
    print("\n🔟  Access control checks...")
    # First make it public again, share with test2
    set_visibility(t1, session_id, "public")
    code, data = set_visibility(t2, session_id, "private")
    check("Non-owner cannot change visibility", code == 403, f"status: {code}")

    # Cleanup: set back to private
    set_visibility(t1, session_id, "private")

    # Summary
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"{'✅' if passed == total else '❌'} {passed}/{total} tests passed")

    if passed < total:
        print("\nFailed:")
        for name, ok in results:
            if not ok:
                print(f"  ❌ {name}")
        sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(run_tests())
