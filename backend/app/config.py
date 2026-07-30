"""Application configuration from environment variables and AWS Secrets Manager.

Configuration for Framewise: Neo4j (bolt) for the graph,
an OpenAI-brained Strands agent, and TwelveLabs (Marengo + Pegasus) for video
understanding. Short-term chat context is kept in-process (see app.memory).
"""

import json
import logging
import os
from typing import Literal

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


def _secret_value(data: dict, *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if value:
            return str(value)
    return None


class Settings(BaseSettings):
    """Application settings loaded from the repo-root .env file."""

    # --- Neo4j (self-hosted, bolt) -----------------------------------------
    neo4j_uri: str = ""
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    # --- AWS Secrets Manager ------------------------------------------------
    # When set, the backend loads Neo4j credentials from this JSON secret and
    # uses .env values only as local fallbacks.
    aws_secrets_manager_secret_name: str = ""
    aws_region: str = ""
    aws_profile: str = ""

    # --- OpenAI (agent reasoning + structured video extraction) ------------
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6"
    openai_extraction_model: str = "gpt-5.6-terra"
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "low"

    # --- TwelveLabs (video understanding) ----------------------------------
    # The SDK auto-reads TWELVE_LABS_API_KEY from the environment; this mirror
    # lets us fail fast with a clear message and pass it explicitly if needed.
    twelve_labs_api_key: str = ""
    # Reuse an existing index by id, or let ingestion create/find one by name.
    tl_index_id: str = ""
    tl_index_name: str = "framewise"
    # Model version strings — config-driven so they can be bumped.
    marengo_model: str = "marengo3.0"          # search/index model on the index
    pegasus_model: str = "pegasus1.2"          # analyze/generate model (index accepts pegasus1.2)
    marengo_embed_model: str = "marengo3.0"  # embed.create model (verified live: 512-dim text embeddings)
    # Neo4j vector index dimension — must match the embed model. The ingest
    # script discovers the true dimension from the first embedding and creates
    # the index accordingly; this is only the default/hint.
    embedding_dimensions: int = 512

    # Public sample clip(s) to ingest when none are supplied. Comma-separated.
    # Big Buck Bunny 720p is the license-clean fallback known to pass TwelveLabs
    # validation; swap in your own clips via SAMPLE_VIDEO_URLS in .env.
    sample_video_urls: str = (
        "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/720/Big_Buck_Bunny_720_10s_5MB.mp4"
    )

    # --- App ----------------------------------------------------------------
    domain_id: str = "framewise"
    backend_port: int = 8000
    frontend_port: int = 3000

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def __init__(self, **values):
        super().__init__(**values)
        self._load_neo4j_from_aws_secret()

    def _load_neo4j_from_aws_secret(self) -> None:
        """Override Neo4j settings from AWS Secrets Manager when configured."""
        if not self.aws_secrets_manager_secret_name:
            return

        try:
            import boto3
        except ImportError:
            logger.warning("AWS secret configured, but boto3 is unavailable.")
            return

        try:
            region = self.aws_region or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
            session_kwargs = {"region_name": region}
            if self.aws_profile:
                session_kwargs["profile_name"] = self.aws_profile
            session = boto3.session.Session(**session_kwargs)
            client = session.client("secretsmanager")
            response = client.get_secret_value(SecretId=self.aws_secrets_manager_secret_name)
            secret_string = response.get("SecretString")
            if not secret_string:
                logger.warning("AWS secret %s has no SecretString.", self.aws_secrets_manager_secret_name)
                return
            secret = json.loads(secret_string)
        except Exception as exc:
            logger.warning("Could not load Neo4j credentials from AWS Secrets Manager: %s", exc)
            return

        self.neo4j_uri = _secret_value(secret, "NEO4J_URI", "neo4j_uri") or self.neo4j_uri
        self.neo4j_username = (
            _secret_value(secret, "NEO4J_USERNAME", "neo4j_username")
            or self.neo4j_username
        )
        self.neo4j_password = (
            _secret_value(secret, "NEO4J_PASSWORD", "neo4j_password")
            or self.neo4j_password
        )
        self.neo4j_database = (
            _secret_value(secret, "NEO4J_DATABASE", "neo4j_database")
            or self.neo4j_database
        )
        logger.info("Loaded Neo4j configuration from AWS Secrets Manager secret %s", self.aws_secrets_manager_secret_name)

    @property
    def sample_video_url_list(self) -> list[str]:
        return [u.strip() for u in self.sample_video_urls.split(",") if u.strip()]


settings = Settings()
