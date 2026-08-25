"""Probe Cvent Bedrock access. Does not print secrets.

Usage (venv on, from repo root):
  python -m harness.check_bedrock

Uses AWS_PROFILE / AWS_REGION / MODEL_* from .env.
Lists foundation models + inference profiles, then optionally Converse
on MODEL_CHEAP if it is set.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    from gateway.config import settings

    profile = (settings.AWS_PROFILE or "").strip() or None
    region = (settings.AWS_REGION or "us-east-1").strip()
    cheap = settings.bedrock_model("cheap")
    strong = settings.bedrock_model("strong")
    auth = "static_keys" if settings.bedrock_has_static_keys() else (
        f"profile={profile}" if profile else "default_chain"
    )
    print(f"auth={auth} region={region}")
    print(f"LLM_PROVIDER={settings.LLM_PROVIDER}")
    print(f"BEDROCK cheap={cheap or '(unset)'} strong={strong or '(unset)'}")
    print(f"compat_configured={settings.compat_configured()} bedrock_configured={settings.bedrock_configured()}")

    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound
    except ImportError:
        print("FAIL: boto3 not installed. pip install -r requirements.txt")
        return 2

    try:
        kw = {"region_name": region}
        if settings.bedrock_has_static_keys():
            kw["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID.strip()
            kw["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY.strip()
            token = (settings.AWS_SESSION_TOKEN or "").strip()
            if token:
                kw["aws_session_token"] = token
        elif profile:
            kw["profile_name"] = profile
        session = boto3.Session(**kw)
        ident = session.client("sts").get_caller_identity()
        print(f"sts.account={ident.get('Account')} arn={ident.get('Arn')}")
    except ProfileNotFound as exc:
        print(f"FAIL: AWS profile missing. {exc}")
        print("This host does not use SSO. Put AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY")
        print("(+ AWS_SESSION_TOKEN if STS) in .env. See WHAT_TO_PROVIDE.md")
        return 2
    except NoCredentialsError as extra:
        print(f"FAIL: no credentials. {extra}")
        print("Fill AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN in .env")
        return 2
    except ClientError as exc:
        print(f"FAIL: sts {exc}")
        return 2

    ctl = session.client("bedrock")
    try:
        fm = ctl.list_foundation_models().get("modelSummaries") or []
    except ClientError as exc:
        print(f"FAIL: list_foundation_models {exc}")
        fm = []
    text_models = [
        m
        for m in fm
        if "TEXT" in (m.get("outputModalities") or [])
        or "ON_DEMAND" in (m.get("inferenceTypesSupported") or [])
    ]
    print(f"foundation_models_textish={len(text_models)} (of {len(fm)} total)")
    for m in text_models[:40]:
        print(
            f"  fm {m.get('modelId')}  "
            f"status={m.get('modelLifecycle', {}).get('status')}  "
            f"infer={m.get('inferenceTypesSupported')}"
        )

    try:
        profiles = []
        token = None
        while True:
            args = {}
            if token:
                args["nextToken"] = token
            page = ctl.list_inference_profiles(**args)
            profiles.extend(page.get("inferenceProfileSummaries") or [])
            token = page.get("nextToken")
            if not token:
                break
    except ClientError as exc:
        print(f"WARN: list_inference_profiles {exc}")
        profiles = []
    print(f"inference_profiles={len(profiles)}")
    for p in profiles[:40]:
        print(f"  ip {p.get('inferenceProfileId')}  name={p.get('inferenceProfileName')}")

    if not cheap:
        print("SKIP converse: MODEL_CHEAP unset. Pick an inference profile id from the list above.")
        return 0

    runtime = session.client("bedrock-runtime")
    print(f"converse MODEL_CHEAP={cheap} ...")
    try:
        resp = runtime.converse(
            modelId=cheap,
            messages=[{"role": "user", "content": [{"text": "Reply with the single word pong."}]}],
            inferenceConfig={"maxTokens": 32},
        )
    except ClientError as exc:
        print(f"FAIL: converse {exc}")
        return 2
    usage = resp.get("usage") or {}
    text = ""
    for block in ((resp.get("output") or {}).get("message") or {}).get("content") or []:
        if block.get("text"):
            text += block["text"]
    print(json.dumps({
        "text": text[:200],
        "inputTokens": usage.get("inputTokens"),
        "outputTokens": usage.get("outputTokens"),
    }, indent=2))
    if "inputTokens" not in usage:
        print("FAIL: no usage in converse response")
        return 2
    print("OK: bedrock converse returned usage")
    return 0


if __name__ == "__main__":
    sys.exit(main())
