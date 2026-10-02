"""Unit and integration tests for the autonomous web search tool."""

import pytest
from src.pipeline.tools.web_search import (
    SearchResultItem,
    QueryEvaluation,
    WebSearchBatchResult,
    normalize_search_query,
    is_safe_url,
    is_result_relevant,
    filter_irrelevant_results,
    search_with_fallback,
    execute_search_batch,
    execute_web_search,
    search_with_sources,
    build_retry_feedback,
    GUARD_OPEN,
    GUARD_CLOSE,
)


class TestQueryNormalization:
    """Test conversational prefix stripping and query cleanup."""

    def test_english_conversational_prefixes(self):
        assert normalize_search_query("can you please search for python langgraph?") == "python langgraph"
        assert normalize_search_query("Tell me what is AWS Bedrock AgentCore") == "AWS Bedrock AgentCore"
        assert normalize_search_query("look up fastmcp tutorial!") == "fastmcp tutorial"

    def test_italian_conversational_prefixes(self):
        assert normalize_search_query("puoi cercarmi documentazione su docker?") == "documentazione su docker"
        assert normalize_search_query("dimmi cos'è LangGraph StateGraph") == "LangGraph StateGraph"
        assert normalize_search_query("vorrei sapere come funziona sqlite fts5") == "come funziona sqlite fts5"

    def test_preserves_technical_identifiers(self):
        assert normalize_search_query("openai.gpt-5.6-luna") == "openai.gpt-5.6-luna"
        assert normalize_search_query("boto3.client('bedrock-runtime')") == "boto3.client('bedrock-runtime')"

    def test_empty_and_whitespace(self):
        assert normalize_search_query("") == ""
        assert normalize_search_query("   ") == ""


class TestSecurityAndSSRF:
    """Test private network, link-local, and AWS IMDS blocking."""

    def test_safe_public_urls(self):
        assert is_safe_url("https://docs.aws.amazon.com/bedrock/") is True
        assert is_safe_url("https://pypi.org/project/langgraph/") is True
        assert is_safe_url("http://example.com/test") is True

    def test_blocks_localhost_and_loopback(self):
        assert is_safe_url("http://localhost:8000/secret") is False
        assert is_safe_url("http://127.0.0.1:8080/mcp") is False
        assert is_safe_url("http://[::1]:8080") is False

    def test_blocks_aws_imds_and_cloud_metadata(self):
        assert is_safe_url("http://169.254.169.254/latest/meta-data/") is False
        assert is_safe_url("http://metadata.google.internal/computeMetadata/v1/") is False

    def test_blocks_private_subnets(self):
        assert is_safe_url("http://10.0.0.5/api") is False
        assert is_safe_url("http://192.168.1.1/admin") is False
        assert is_safe_url("http://172.16.0.1:9000") is False

    def test_blocks_non_http_schemes(self):
        assert is_safe_url("file:///etc/passwd") is False
        assert is_safe_url("gopher://server.local") is False
        assert is_safe_url("ftp://ftp.example.com") is False


class TestRelevanceFiltering:
    """Test semantic term overlap checking."""

    def test_relevant_result(self):
        query = "python langgraph stateful agent"
        title = "LangGraph Tutorial: Build Stateful Agents in Python"
        snippet = "LangGraph is an orchestration library to build stateful multi-agent systems."
        assert is_result_relevant(query, title, snippet) is True

    def test_irrelevant_spam_result(self):
        query = "python langgraph"
        title = "Best Cheap Hotels in Rome"
        snippet = "Find luxury rooms and discount flight packages for summer holidays."
        assert is_result_relevant(query, title, snippet) is False

    def test_filter_list(self):
        query = "sqlite database"
        results = [
            SearchResultItem(title="SQLite Home Page", url="https://sqlite.org", snippet="Self-contained SQL database engine"),
            SearchResultItem(title="Cooking Pizza Dough", url="https://pizza.com", snippet="Flour, yeast, and olive oil recipe")
        ]
        kept = filter_irrelevant_results(query, results)
        assert len(kept) == 1
        assert kept[0].title == "SQLite Home Page"


class TestLiveWebSearchAndBatch:
    """Live web search tests using cascading providers (ddgs / HTML)."""

    def test_search_with_fallback_live(self):
        results, provider = search_with_fallback("python programming language", count=2)
        assert len(results) >= 1
        assert provider != "none"
        for r in results:
            assert r.url.startswith("http")
            assert is_safe_url(r.url)
            assert len(r.title) > 0

    def test_execute_search_batch_with_prompt_guards(self):
        batch = execute_search_batch(["python programming", "sqlite database"], count_per_query=2)
        assert batch.has_satisfactory_results is True
        assert len(batch.source_urls) >= 1
        assert batch.formatted_markdown.startswith(GUARD_OPEN)
        assert batch.formatted_markdown.endswith(GUARD_CLOSE)
        assert "Verified Web Documentation Context" in batch.formatted_markdown

    def test_standard_execute_web_search(self):
        markdown = execute_web_search(["python documentation"])
        assert isinstance(markdown, str)
        assert GUARD_OPEN in markdown
        assert GUARD_CLOSE in markdown

    def test_search_with_sources(self):
        markdown, urls = search_with_sources(["python programming"])
        assert isinstance(markdown, str)
        assert isinstance(urls, list)
        assert len(urls) >= 1

    def test_zero_results_and_retry_feedback(self):
        nonsense = "xyzqwerty987nonexistentdomain123456789"
        batch = execute_search_batch([nonsense])
        assert batch.has_satisfactory_results is False
        assert batch.needs_retry is True
        assert batch.retry_feedback is not None
        assert nonsense in batch.retry_feedback
        assert "Instructions for Query Reformulation" in batch.retry_feedback

    def test_empty_query_list_resilience(self):
        markdown = execute_web_search([])
        assert "No search queries specified" in markdown
        markdown, sources = search_with_sources([])
        assert sources == []
