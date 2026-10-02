"""Unit tests for the centralized model factory (Bedrock & Bedrock Mantle dual provider)."""

import pytest
from unittest.mock import patch, MagicMock
from langchain_aws import ChatBedrockConverse
from langchain_openai import ChatOpenAI

from src.core.config import settings
from src.core.models import (
    get_chat_model,
    get_fast_model,
    get_reasoner_model,
    has_active_model_credentials,
)
from src.core.schemas import ChunkClassification


def test_get_chat_model_bedrock():
    """Verify that provider='bedrock' instantiates ChatBedrockConverse with SigV4/region."""
    with patch.object(settings, "aws_region", "us-west-2"), \
         patch.object(settings, "aws_access_key_id", "test-key"), \
         patch.object(settings, "aws_secret_access_key", "test-secret"), \
         patch.object(settings, "aws_session_token", "test-token"):
        
        model = get_chat_model(
            provider="bedrock",
            model_id="amazon.nova-micro-v1:0",
            temperature=0.1,
        )
        assert isinstance(model, ChatBedrockConverse)
        assert model.model == "amazon.nova-micro-v1:0"
        assert model.region_name == "us-west-2"
        assert model.temperature == 0.1


def test_get_chat_model_mantle_with_static_key():
    """Verify that provider='mantle' instantiates ChatOpenAI with Mantle endpoint and API key."""
    with patch.object(settings, "mantle_endpoint", "https://bedrock-mantle.us-east-1.api.aws/openai/v1"), \
         patch.object(settings, "mantle_api_key", "bedrock-api-key-test-12345"):
        
        model = get_chat_model(
            provider="mantle",
            model_id="amazon.nova-micro-v1:0",
            temperature=0.0,
        )
        assert isinstance(model, ChatOpenAI)
        assert model.model_name == "amazon.nova-micro-v1:0"
        assert str(model.openai_api_base).rstrip("/") == "https://bedrock-mantle.us-east-1.api.aws/openai/v1"
        assert model.openai_api_key.get_secret_value() == "bedrock-api-key-test-12345"


def test_get_chat_model_mantle_auto_mint_token():
    """Verify that provider='mantle' auto-mints token when static key is absent."""
    with patch.object(settings, "mantle_endpoint", "https://bedrock-mantle.us-east-1.api.aws/openai/v1"), \
         patch.object(settings, "mantle_api_key", None), \
         patch.object(settings, "aws_region", "us-east-1"), \
         patch("aws_bedrock_token_generator.provide_token", return_value="minted-bearer-token-xyz") as mock_mint:
        
        model = get_chat_model(
            provider="mantle",
            model_id="amazon.nova-micro-v1:0",
        )
        assert isinstance(model, ChatOpenAI)
        assert model.openai_api_key.get_secret_value() == "minted-bearer-token-xyz"
        mock_mint.assert_called_once_with(region="us-east-1")


def test_get_chat_model_unsupported_provider():
    """Verify that an unknown provider string raises a ValueError."""
    with pytest.raises(ValueError, match="Unsupported provider 'invalid_provider'"):
        get_chat_model(provider="invalid_provider", model_id="some-model")


def test_has_active_model_credentials():
    """Test credential detection for both bedrock and mantle providers."""
    from unittest.mock import PropertyMock

    # Bedrock: requires AWS IAM credentials
    with patch.object(type(settings), "has_aws_credentials", new_callable=PropertyMock, return_value=True):
        assert has_active_model_credentials("bedrock") is True

    with patch.object(type(settings), "has_aws_credentials", new_callable=PropertyMock, return_value=False):
        assert has_active_model_credentials("bedrock") is False

    # Mantle: requires mantle_api_key or AWS IAM credentials
    with patch.object(settings, "mantle_api_key", "bedrock-api-key-123"):
        assert has_active_model_credentials("mantle") is True

    with patch.object(settings, "mantle_api_key", None), \
         patch.object(type(settings), "has_aws_credentials", new_callable=PropertyMock, return_value=True):
        assert has_active_model_credentials("mantle") is True

    with patch.object(settings, "mantle_api_key", None), \
         patch.object(type(settings), "has_aws_credentials", new_callable=PropertyMock, return_value=False):
        assert has_active_model_credentials("mantle") is False


def test_structured_output_binding():
    """Verify that .with_structured_output works on both provider model instances."""
    with patch.object(settings, "aws_access_key_id", "test"), \
         patch.object(settings, "aws_secret_access_key", "test"):
        bedrock_model = get_chat_model("bedrock", "amazon.nova-micro-v1:0")
        bedrock_structured = bedrock_model.with_structured_output(ChunkClassification)
        assert bedrock_structured is not None

    with patch.object(settings, "mantle_api_key", "bedrock-api-key-123"):
        mantle_model = get_chat_model("mantle", "amazon.nova-micro-v1:0")
        mantle_structured = mantle_model.with_structured_output(ChunkClassification)
        assert mantle_structured is not None


def test_fast_and_reasoner_getters():
    """Verify get_fast_model and get_reasoner_model respect provider and model configuration."""
    with patch.object(settings, "gatekeeper_provider", "bedrock"), \
         patch.object(settings, "gatekeeper_model_id", "amazon.nova-micro-v1:0"), \
         patch.object(settings, "aws_access_key_id", "test"), \
         patch.object(settings, "aws_secret_access_key", "test"):
        fast = get_fast_model()
        assert isinstance(fast, ChatBedrockConverse)
        assert fast.model == "amazon.nova-micro-v1:0"

    with patch.object(settings, "reasoner_provider", "mantle"), \
         patch.object(settings, "reasoner_model_id", "anthropic.claude-3-5-sonnet-20241022-v2:0"), \
         patch.object(settings, "mantle_api_key", "bedrock-api-key-123"):
        reasoner = get_reasoner_model()
        assert isinstance(reasoner, ChatOpenAI)
        assert reasoner.model_name == "anthropic.claude-3-5-sonnet-20241022-v2:0"
