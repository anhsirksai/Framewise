"""Create or update the Framewise Neo4j Aura secret in AWS Secrets Manager.

Reads Neo4j values from the repo-root .env file and writes this JSON payload:
  NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE

The script does not print secret values.

Run:
  uv run python scripts/sync_neo4j_secret.py --name framewise/neo4j-aura
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import dotenv_values


DEFAULT_SECRET_NAME = "framewise/neo4j-aura"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Neo4j Aura credentials to AWS Secrets Manager.")
    parser.add_argument("--name", default=os.getenv("AWS_SECRETS_MANAGER_SECRET_NAME", DEFAULT_SECRET_NAME))
    parser.add_argument("--region", default=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1")
    parser.add_argument("--profile", default=os.getenv("AWS_PROFILE") or "")
    parser.add_argument("--env-file", default=str(Path(__file__).resolve().parents[2] / ".env"))
    return parser.parse_args()


def load_neo4j_secret(env_file: str) -> dict[str, str]:
    values = dotenv_values(env_file)
    required = ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"]
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise RuntimeError(f"Missing required .env values: {', '.join(missing)}")

    return {
        "NEO4J_URI": str(values["NEO4J_URI"]),
        "NEO4J_USERNAME": str(values["NEO4J_USERNAME"]),
        "NEO4J_PASSWORD": str(values["NEO4J_PASSWORD"]),
        "NEO4J_DATABASE": str(values.get("NEO4J_DATABASE") or "neo4j"),
    }


def main() -> int:
    import botocore.exceptions
    import boto3

    args = parse_args()
    payload = load_neo4j_secret(args.env_file)
    session_kwargs = {"region_name": args.region}
    if args.profile:
        session_kwargs["profile_name"] = args.profile
    client = boto3.session.Session(**session_kwargs).client("secretsmanager")
    secret_string = json.dumps(payload)

    try:
        response = client.create_secret(
            Name=args.name,
            Description="Framewise Neo4j Aura connection settings",
            SecretString=secret_string,
        )
        action = "created"
        arn = response.get("ARN", "")
    except botocore.exceptions.ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ResourceExistsException":
            raise
        response = client.put_secret_value(
            SecretId=args.name,
            SecretString=secret_string,
        )
        action = "updated"
        arn = response.get("ARN", "")

    print(f"AWS Secrets Manager secret {action}: {args.name}")
    if arn:
        print(f"ARN: {arn}")
    print("Stored keys: NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE")
    print(f"Set AWS_SECRETS_MANAGER_SECRET_NAME={args.name} to load it at runtime.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

