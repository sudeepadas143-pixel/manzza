"""The embedding cache must survive filling up in the middle of a batch (it once dropped texts the
batch still needed and the narrative read crashed with a KeyError)."""
import numpy as np

from radar import embed


class _Enc:
    def __init__(self, n):
        self.ids = [n % 7 + 1, 2, 3]
        self.attention_mask = [1, 1, 1]


class _Tok:
    def encode_batch(self, texts):
        return [_Enc(len(t)) for t in texts]


class _Sess:
    def run(self, _, feeds):
        ids = feeds["input_ids"]
        return [np.repeat(ids[..., None].astype(np.float32), 4, axis=2) + 1.0]


def test_cache_full_mid_batch_keeps_every_text(monkeypatch):
    e = object.__new__(embed.Embedder)
    e.np, e.tok, e.sess, e.inputs, e.cache = np, _Tok(), _Sess(), {"input_ids", "attention_mask"}, {}
    e.embed(["a", "bb"])
    e.cache.update({f"x{i}": np.zeros(4, np.float16) for i in range(60000)})
    out = e.embed(["a", "bb", "new text"])        # 'a' and 'bb' cached, the new one tips it over
    assert out.shape == (3, 4) and len(e.cache) == 3
