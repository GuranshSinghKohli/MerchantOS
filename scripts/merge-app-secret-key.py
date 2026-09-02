#!/usr/bin/env python3
"""Merge one key into merchantos-*/app without printing secret values."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret-id", default="merchantos-staging/app")
    parser.add_argument("--key", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument(
        "--from-env",
        help="Read the value from this environment variable (not printed)",
    )
    args = parser.parse_args()
    if args.from_env:
        import os

        value = os.environ.get(args.from_env, "")
        if not value:
            print(f"environment {args.from_env} is empty", file=sys.stderr)
            return 2
    else:
        value = sys.stdin.read().strip()
        if not value:
            print("stdin is empty", file=sys.stderr)
            return 2
    raw = subprocess.check_output(
        [
            "aws",
            "secretsmanager",
            "get-secret-value",
            "--region",
            args.region,
            "--secret-id",
            args.secret_id,
            "--query",
            "SecretString",
            "--output",
            "text",
        ],
        text=True,
    )
    payload = json.loads(raw)
    payload[args.key] = value
    subprocess.check_call(
        [
            "aws",
            "secretsmanager",
            "put-secret-value",
            "--region",
            args.region,
            "--secret-id",
            args.secret_id,
            "--secret-string",
            json.dumps(payload),
        ]
    )
    print(f"merged {args.key} into {args.secret_id} (value not printed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
