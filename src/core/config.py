"""Configuration module for EXAMEN."""

import os
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # AWS & Bedrock
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    aws_access_key_id: str | None = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = Field(default=None, alias="AWS_SECRET_ACCESS_KEY")
    aws_session_token: str | None = Field(default=None, alias="AWS_SESSION_TOKEN")

    # Provider Selection: "bedrock" or "mantle" (independently configurable!)
    gatekeeper_provider: Literal["bedrock", "mantle"] = Field(
        default="bedrock", alias="GATEKEEPER_PROVIDER"
    )
    reasoner_provider: Literal["bedrock", "mantle"] = Field(
        default="bedrock", alias="REASONER_PROVIDER"
    )

    # Bedrock Mantle Endpoint & Credentials
    mantle_endpoint: str | None = Field(default=None, alias="BEDROCK_MANTLE_ENDPOINT")
    mantle_api_key: str | None = Field(default=None, alias="BEDROCK_MANTLE_API_KEY")

    # Bedrock Foundation Models
    gatekeeper_model_id: str = Field(
        default="openai.gpt-5.6-luna",
        alias="BEDROCK_GATEKEEPER_MODEL"
    )
    reasoner_model_id: str = Field(
        default="anthropic.claude-3-5-sonnet-20241022-v2:0",
        alias="BEDROCK_REASONER_MODEL"
    )

    # Storage Backend
    storage_backend: Literal["sqlite", "dynamo", "agentcore_memory"] = Field(
        default="sqlite",
        alias="STORAGE_BACKEND"
    )
    sqlite_db_path: str = Field(default="examen.db", alias="SQLITE_DB_PATH")

    # Development & Testing
    mock_ai: bool = Field(default=False, alias="MOCK_AI")
    agentcore_runtime_arn: str | None = Field(default=None, alias="AGENTCORE_RUNTIME_ARN")

    # Deep Topic Event Engine (docs/next_steps/deep_topic_event_engine/)
    event_engine_enabled: bool = Field(default=True, alias="EVENT_ENGINE_ENABLED")
    event_profile: Literal["default", "demo"] = Field(default="default", alias="EVENT_PROFILE")
    event_t_soft_seconds: float = Field(default=300.0, alias="EVENT_T_SOFT_SECONDS")
    event_t_hard_seconds: float = Field(default=1800.0, alias="EVENT_T_HARD_SECONDS")
    event_t_hard_after_close_cue_seconds: float = Field(
        default=300.0, alias="EVENT_T_HARD_AFTER_CLOSE_CUE_SECONDS"
    )
    event_t_hard_transit_seconds: float = Field(default=120.0, alias="EVENT_T_HARD_TRANSIT_SECONDS")
    event_t_checkpoint_seconds: float = Field(default=1200.0, alias="EVENT_T_CHECKPOINT_SECONDS")
    event_min_segment_words: int = Field(default=300, alias="EVENT_MIN_SEGMENT_WORDS")
    event_location_shift_meters: float = Field(default=400.0, alias="EVENT_LOCATION_SHIFT_METERS")
    event_tick_seconds: float = Field(default=15.0, alias="EVENT_TICK_SECONDS")
    event_synthesis_max_words: int = Field(default=6000, alias="EVENT_SYNTHESIS_MAX_WORDS")

    # Serving & MCP
    mcp_host: str = Field(default="0.0.0.0", alias="MCP_HOST")
    mcp_port: int = Field(default=8000, alias="MCP_PORT")
    mcp_streamable_http: bool = Field(default=True, alias="MCP_STREAMABLE_HTTP")

    @property
    def has_aws_credentials(self) -> bool:
        if self.aws_access_key_id and self.aws_secret_access_key:
            return True
        try:
            import boto3
            session = boto3.Session(
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                aws_session_token=self.aws_session_token,
                region_name=self.aws_region
            )
            return session.get_credentials() is not None
        except Exception:
            return False

    @property
    def has_mantle_credentials(self) -> bool:
        if self.mantle_api_key and self.mantle_api_key.strip():
            return True
        return self.has_aws_credentials

    def get_mantle_endpoint(self) -> str:
        """Returns configured Mantle endpoint or default regional AWS endpoint."""
        if self.mantle_endpoint and self.mantle_endpoint.strip():
            return self.mantle_endpoint.strip()
        return f"https://bedrock-mantle.{self.aws_region}.api.aws/openai/v1"

    def get_mantle_api_key(self) -> str:
        """Returns static Mantle API key, or dynamically mints a short-term key from IAM role."""
        if self.mantle_api_key and self.mantle_api_key.strip():
            return self.mantle_api_key.strip()
        try:
            import os
            if self.aws_access_key_id and not os.environ.get("AWS_ACCESS_KEY_ID"):
                os.environ["AWS_ACCESS_KEY_ID"] = self.aws_access_key_id
            if self.aws_secret_access_key and not os.environ.get("AWS_SECRET_ACCESS_KEY"):
                os.environ["AWS_SECRET_ACCESS_KEY"] = self.aws_secret_access_key
            if self.aws_session_token and not os.environ.get("AWS_SESSION_TOKEN"):
                os.environ["AWS_SESSION_TOKEN"] = self.aws_session_token
            if self.aws_region and not os.environ.get("AWS_REGION"):
                os.environ["AWS_REGION"] = self.aws_region
                os.environ["AWS_DEFAULT_REGION"] = self.aws_region

            from aws_bedrock_token_generator import provide_token
            return provide_token(region=self.aws_region)
        except Exception as e:
            raise ValueError(
                f"No BEDROCK_MANTLE_API_KEY configured and failed to mint token from IAM credentials: {e}"
            )


settings = Settings()

