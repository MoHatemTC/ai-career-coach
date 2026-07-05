from unittest.mock import patch
from app.ai.registry import LLMServiceRegistry
from app.core.embeddings import EMBEDDING_MODEL


def test_registry_local_embedder_routing():
    """registry.embed routes to the local embedder when model='local'."""
    with patch(
        "app.core.embeddings.embed", return_value=[[0.1, 0.2, 0.3]]
    ) as mock_embed:
        registry = LLMServiceRegistry(default_embedding_model="text-embedding-ada-002")
        result = registry.embed(["hello world"], model="local")

        mock_embed.assert_called_once_with(["hello world"])
        assert result == [[0.1, 0.2, 0.3]]


def test_registry_local_embedder_routing_by_model_name():
    """registry.embed routes to the local embedder for the configured model id."""
    with patch(
        "app.core.embeddings.embed", return_value=[[0.1, 0.2, 0.3]]
    ) as mock_embed:
        registry = LLMServiceRegistry(default_embedding_model="text-embedding-ada-002")
        result = registry.embed(["hello world"], model=EMBEDDING_MODEL)

        mock_embed.assert_called_once_with(["hello world"])
        assert result == [[0.1, 0.2, 0.3]]


def test_registry_local_embedder_routing_default():
    """registry.embed routes to the local embedder when it is the default model."""
    with patch(
        "app.core.embeddings.embed", return_value=[[0.1, 0.2, 0.3]]
    ) as mock_embed:
        registry = LLMServiceRegistry(default_embedding_model=EMBEDDING_MODEL)
        result = registry.embed(["hello world"])

        mock_embed.assert_called_once_with(["hello world"])
        assert result == [[0.1, 0.2, 0.3]]
