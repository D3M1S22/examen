"""Centralized Model Factory for AWS Bedrock & Bedrock Mantle.

Provides dynamic, provider-agnostic model instantiation supporting both:
1. Native AWS Bedrock Converse API (via langchain_aws.ChatBedrockConverse)
2. Amazon Bedrock Mantle OpenAI-compatible API (via langchain_openai.ChatOpenAI)
"""

from __future__ import annotations

import logging
from typing import Literal, Optional
from langchain_core.language_models.chat_models import BaseChatModel

from src.core.config import Settings, settings

logger = logging.getLogger("examen.core.models")


def get_chat_model(
    provider: Literal["bedrock", "mantle"],
    model_id: str,
    temperature: float = 0.0,
    cfg: Optional[Settings] = None,
) -> BaseChatModel:
    """Instantiates a chat model configured for Bedrock or Bedrock Mantle.

    Args:
        provider: "bedrock" for native Converse API, "mantle" for OpenAI-compatible endpoint.
        model_id: Model identifier (e.g. 'openai.gpt-5.6-luna', 'anthropic.claude-3-5-sonnet-20241022-v2:0').
        temperature: Sampling temperature (default 0.0 for deterministic extraction).
        cfg: Settings to read region, endpoint and credentials from (default: the live settings;
            the admin console passes a candidate copy to test a change before saving it).

    Returns:
        A BaseChatModel instance supporting .invoke(), .ainvoke(), and .with_structured_output().
    """
    s = cfg or settings
    if provider == "mantle":
        from langchain_openai import ChatOpenAI

        endpoint = s.get_mantle_endpoint()
        api_key = s.get_mantle_api_key()
        logger.debug(f"Initializing Bedrock Mantle ChatOpenAI: model={model_id}, endpoint={endpoint}")

        return ChatOpenAI(
            model=model_id,
            base_url=endpoint,
            api_key=api_key,
            temperature=temperature,
        )
    elif provider == "bedrock":
        from langchain_aws import ChatBedrockConverse

        logger.debug(f"Initializing AWS Bedrock Converse: model={model_id}, region={s.aws_region}")
        return ChatBedrockConverse(
            model=model_id,
            region_name=s.aws_region,
            temperature=temperature,
            aws_access_key_id=s.aws_access_key_id,
            aws_secret_access_key=s.aws_secret_access_key,
            aws_session_token=s.aws_session_token,
            disable_streaming=True,
        )
    else:
        raise ValueError(f"Unsupported provider '{provider}'. Must be 'bedrock' or 'mantle'.")


def get_fast_model() -> BaseChatModel:
    """Returns the configured lightweight model for Gatekeeper, Action State, Social, and Topic extraction."""
    return get_chat_model(
        provider=settings.gatekeeper_provider,
        model_id=settings.gatekeeper_model_id,
        temperature=0.0,
    )


def get_reasoner_model() -> BaseChatModel:
    """Returns the configured deep reasoner model for Topic Research synthesis."""
    return get_chat_model(
        provider=settings.reasoner_provider,
        model_id=settings.reasoner_model_id,
        temperature=0.2,
    )


def has_active_model_credentials(provider: Literal["bedrock", "mantle"]) -> bool:
    """Helper to check if active credentials exist for the selected provider."""
    if provider == "mantle":
        return settings.has_mantle_credentials
    return settings.has_aws_credentials


def get_embedding_model(cfg: Optional[Settings] = None):
    """Returns the Bedrock text embedding model used for topic continuity (Titan Text Embeddings V2 by default).

    Embeddings always use the native Bedrock runtime (Mantle exposes chat models only).
    """
    from langchain_aws import BedrockEmbeddings

    s = cfg or settings
    model_kwargs = {"dimensions": s.embedding_dimensions, "normalize": True}
    if not s.embedding_model_id.startswith("amazon.titan-embed-text-v2"):
        model_kwargs = {}  # dimensions/normalize are Titan V2 specific
    return BedrockEmbeddings(
        model_id=s.embedding_model_id,
        region_name=s.aws_region,
        aws_access_key_id=s.aws_access_key_id,
        aws_secret_access_key=s.aws_secret_access_key,
        aws_session_token=s.aws_session_token,
        model_kwargs=model_kwargs or None,
    )
