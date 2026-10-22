"""Optional semantic grouping of narrative terms with all-MiniLM-L6-v2.

Model: sentence-transformers/all-MiniLM-L6-v2 (Apache-2.0), the ONNX export published in the
model's Hugging Face repo, run with onnxruntime (MIT) and tokenizers (Apache-2.0). No PyTorch,
so it fits in the desktop app. The 23 MB quantized model is downloaded once from
huggingface.co into <data dir>/models on first start; without it (or without the optional
packages) narrative detection stays purely lexical.

Used for one thing: merging narrative clusters whose head terms mean the same
(cat/kitty/kitten, frog/toad, trump/president). Threshold 0.72 was set by inspecting pairs:
it merges those while keeping cat/dog (0.66) and dog/doge (0.65) apart. Every merge is
recorded in the meta's evidence with its similarity, so it stays explainable.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path

log = logging.getLogger("radar.embed")

REPO = "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/"
FILES = {  # name -> (path in repo, size in bytes) ; size guards against truncated downloads
    "model.onnx": ("onnx/model_quint8_avx2.onnx", 23_046_789),
    "tokenizer.json": ("tokenizer.json", 466_247),
}
THRESHOLD = 0.72


class Embedder:
    _inst: "Embedder | None" = None
    _lock = threading.Lock()

    def __init__(self, model_dir: Path):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np = np
        self.tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.tok.enable_padding(pad_id=0, pad_token="[PAD]")
        self.tok.enable_truncation(max_length=96)    # names are short; linked post text needs more
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2            # stay light next to the collector
        self.sess = ort.InferenceSession(str(model_dir / "model.onnx"), opts, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.sess.get_inputs()}
        self.cache: dict[str, object] = {}

    @classmethod
    def get(cls) -> "Embedder | None":
        return cls._inst

    def embed(self, texts: list[str]):
        np = self.np
        todo = [t for t in dict.fromkeys(texts) if t not in self.cache]
        if todo:
            enc = self.tok.encode_batch(todo)
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            am = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feeds = {"input_ids": ids, "attention_mask": am, "token_type_ids": np.zeros_like(ids)}
            out = self.sess.run(None, {k: v for k, v in feeds.items() if k in self.inputs})[0]
            v = (out * am[..., None]).sum(1) / np.maximum(am.sum(1, keepdims=True), 1)
            v = v / np.linalg.norm(v, axis=1, keepdims=True)
            if len(self.cache) + len(todo) > 60000:
                self.cache.clear()
            for t, row in zip(todo, v):
                self.cache[t] = row.astype(np.float16)    # 768 bytes per text
        return np.stack([self.cache[t] for t in texts]).astype(np.float32)

    def embed_many(self, texts: list[str], batch: int = 256):
        """Embed in batches (long lists would build one huge padded tensor)."""
        np = self.np
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)
        return np.concatenate([self.embed(texts[i:i + batch]) for i in range(0, len(texts), batch)])


def ensure_model(model_dir: Path, http_get=None) -> bool:
    """Download the model files if missing. Returns True when both are present and complete."""
    model_dir.mkdir(parents=True, exist_ok=True)
    for name, (path, size) in FILES.items():
        dest = model_dir / name
        if dest.exists() and dest.stat().st_size == size:
            continue
        import httpx
        tmp = dest.with_suffix(".part")
        with httpx.stream("GET", REPO + path, follow_redirects=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        if tmp.stat().st_size != size:
            tmp.unlink(missing_ok=True)
            raise IOError(f"{name}: unexpected size")
        tmp.replace(dest)
    return True


def load(model_dir: Path) -> bool:
    """Make the shared Embedder available (downloading the model first if needed)."""
    try:
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
    except ImportError:
        log.info("semantic narrative grouping off: onnxruntime/tokenizers not installed")
        return False
    try:
        ensure_model(model_dir)
        with Embedder._lock:
            Embedder._inst = Embedder(model_dir)
        log.info("semantic narrative grouping on (all-MiniLM-L6-v2)")
        return True
    except Exception as exc:  # no network, CPU without AVX2, corrupt file: stay lexical
        log.warning("semantic narrative grouping off: %s", exc)
        return False


def merge_clusters(clusters: list[list[str]], threshold: float = THRESHOLD) -> tuple[list[list[str]], list[list]]:
    """Merge clusters whose head terms are near-synonyms. Returns (clusters, merges) where
    each merge is [kept_head, merged_head, similarity]. Clusters stay in activity order."""
    emb = Embedder.get()
    if emb is None or len(clusters) < 2:
        return clusters, []
    heads = [c[0] for c in clusters]
    vec = emb.embed(heads)
    sims = vec @ vec.T
    out: list[list[str]] = []
    owner: dict[int, int] = {}
    merges: list[list] = []
    for i, c in enumerate(clusters):
        for j in range(i):                      # the earlier (more active) cluster absorbs
            if j in owner and sims[i, j] >= threshold:
                k = owner[j]
                out[k] += [t for t in c if t not in out[k]]
                owner[i] = k
                merges.append([out[k][0], heads[i], round(float(sims[i, j]), 2)])
                break
        else:
            owner[i] = len(out)
            out.append(list(c))
    return out, merges


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
