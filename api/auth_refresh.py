"""
/auth/refresh handler — exchanges a refresh_token for a fresh id_token.

Called silently by the SPA when the id_token is about to expire, avoiding
a disruptive full-page redirect to the IdP.

Flow:
  SPA (background fetch) ─── POST /api/auth/refresh ──▶  POST Federate /oauth2/v2/token
  { refresh_token }                                       { grant_type=refresh_token, ... }
  Stores new id_token    ◀─── { id_token, expires_in }
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

FEDERATE_TOKEN_URL = os.environ.get(
    "FEDERATE_TOKEN_URL",
    "https://idp.federate.amazon.com/api/oauth2/v2/token",
)
FEDERATE_SECRET_ARN = os.environ["FEDERATE_SECRET_ARN"]

_secrets = boto3.client("secretsmanager", region_name="us-east-1")
_secret_cache: dict | None = None


def _get_secret() -> dict:
    global _secret_cache
    if _secret_cache is None:
        r = _secrets.get_secret_value(SecretId=FEDERATE_SECRET_ARN)
        _secret_cache = json.loads(r["SecretString"])
    return _secret_cache


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        refresh_token = body.get("refresh_token", "").strip()

        if not refresh_token:
            return _response(400, {"error": "refresh_token is required"})

        secret = _get_secret()
        client_id = secret["client_id"]
        client_secret = secret["client_secret"]

        form = urllib.parse.urlencode({
            "grant_type":     "refresh_token",
            "refresh_token":  refresh_token,
            "client_id":      client_id,
            "client_secret":  client_secret,
        }).encode()

        req = urllib.request.Request(
            FEDERATE_TOKEN_URL,
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                tokens = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            err_body = e.read().decode(errors="replace")
            return _response(e.code, {"error": "Token refresh failed", "detail": err_body})

        return _response(200, {
            "id_token":      tokens.get("id_token"),
            "token_type":    tokens.get("token_type", "Bearer"),
            "expires_in":    tokens.get("expires_in", 3600),
            "refresh_token": tokens.get("refresh_token", refresh_token),
        })

    except Exception as e:
        logger.exception("Unexpected error in auth_refresh")
        return _response(500, {"error": "Internal server error"})


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type":                "application/json",
            "Access-Control-Allow-Origin": os.environ.get("ALLOWED_ORIGIN", "*"),
        },
        "body": json.dumps(body),
    }
