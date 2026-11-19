from pathlib import Path

import numpy as np
import pytest
from model2vec import StaticModel
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace


@pytest.fixture(scope="module")
def local_model(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Save a minimal real CPU encoder for integration tests with empty Hub caches."""
    words = ["[UNK]", "cache", "key", "def", "class", "enrich", "semantic", "queries"]
    tokenizer = Tokenizer(WordLevel({word: index for index, word in enumerate(words)}, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = Whitespace()
    model = StaticModel(np.eye(len(words), dtype=np.float32), tokenizer, normalize=True)
    path = tmp_path_factory.mktemp("local-model")
    model.save_pretrained(path)
    return path
