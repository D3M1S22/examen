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

    # Bedrock Foundation Models
    gatekeeper_model_id: str = Field(
        default="anthropic.claude-3-5-haiku-20241022-v1:0",
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

    # Serving & MCP
    mcp_host: str = Field(default="0.0.0.0", alias="MCP_HOST")
    mcp_port: int = Field(default=8000, alias="MCP_PORT")
    mcp_streamable_http: bool = Field(default=True, alias="MCP_STREAMABLE_HTTP")

    # Optional Search API
    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")


settings = Settings()
