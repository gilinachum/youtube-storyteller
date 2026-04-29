"""Helper to extract the caller's email from an API Gateway event.

Reads email from the request (body, query string). No auth enforcement —
the caller is trusted. Fine for demos and solo use.

For multi-tenant deployments, add an API Gateway authorizer (JWT, IAM,
or custom Lambda) that populates `requestContext.authorizer.email`; this
helper prefers that source if present.
"""
import json


def caller_email(event: dict) -> str:
    """Return the caller's email (always lowercased). '' if missing."""
    # 1. Authorizer context (populated by an overlay authorizer if present)
    ctx = (event.get("requestContext") or {}).get("authorizer") or {}
    email = ctx.get("email") or ctx.get("principalId") or ""
    if email:
        return email.strip().lower()

    # 2. Query string
    qs = event.get("queryStringParameters") or {}
    email = (qs.get("email") or "").strip().lower()
    if email:
        return email

    # 3. JSON body
    body = event.get("body")
    if body:
        try:
            data = json.loads(body) if isinstance(body, str) else body
            email = (data.get("email") or "").strip().lower()
        except Exception:
            pass

    return email
