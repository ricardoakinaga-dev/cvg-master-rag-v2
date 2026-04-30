import importlib
import sys
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _reload_config():
    return importlib.reload(importlib.import_module("core.config"))


def _reload_embedding_service():
    return importlib.reload(importlib.import_module("services.embedding_service"))


def test_embedding_model_env_takes_precedence_over_legacy_name(monkeypatch):
    with monkeypatch.context() as scoped:
        scoped.setenv("EMBEDDING_MODEL", "text-embedding-3-large")
        scoped.setenv("EMBEDDING_EMBEDDING_MODEL", "legacy-embedding-model")

        config = _reload_config()

        assert config.EMBEDDING_MODEL == "text-embedding-3-large"

    _reload_config()


def test_embedding_model_legacy_name_remains_supported(monkeypatch):
    with monkeypatch.context() as scoped:
        scoped.delenv("EMBEDDING_MODEL", raising=False)
        scoped.setenv("EMBEDDING_EMBEDDING_MODEL", "legacy-embedding-model")

        config = _reload_config()

        assert config.EMBEDDING_MODEL == "legacy-embedding-model"

    _reload_config()


def test_embedding_service_uses_configured_embedding_model(monkeypatch):
    with monkeypatch.context() as scoped:
        scoped.setenv("EMBEDDING_MODEL", "model-from-primary-env")
        scoped.setenv("OPENAI_API_KEY", "test-key")

        _reload_config()
        embedding_service = _reload_embedding_service()

        class FakeEmbeddingsAPI:
            def __init__(self):
                self.model = None

            def create(self, *, model, input):
                self.model = model

                class Response:
                    data = [type("Item", (), {"embedding": [0.1] * 1536})()]

                return Response()

        fake_api = FakeEmbeddingsAPI()
        fake_client = type(
            "FakeClient",
            (),
            {
                "api_key": "test-key",
                "embeddings": fake_api,
            },
        )()

        scoped.setattr(embedding_service, "client", fake_client)

        embedding_service.get_embedding("texto")

        assert fake_api.model == "model-from-primary-env"

    _reload_config()
    _reload_embedding_service()
