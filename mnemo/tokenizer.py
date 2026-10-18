"""Mnemo's own byte-level BPE tokenizer, trained from scratch on the first text it reads."""

from __future__ import annotations

from typing import Iterable

from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers

from .config import TOKENIZER_PATH

VOCAB_SIZE = 32000
EOT = "<|endoftext|>"
USER, ASSISTANT, SYSTEM, END = "<|user|>", "<|assistant|>", "<|system|>", "<|end|>"
MEM_OPEN, MEM_CLOSE = "<|memory|>", "<|/memory|>"
PAGE_OPEN, PAGE_CLOSE, GOAL, ACTION = "<|page|>", "<|/page|>", "<|goal|>", "<|action|>"
SPECIAL = [EOT, USER, ASSISTANT, SYSTEM, END, MEM_OPEN, MEM_CLOSE, PAGE_OPEN, PAGE_CLOSE, GOAL, ACTION, "<|pad|>"]


def train(texts: Iterable[str], vocab_size: int = VOCAB_SIZE) -> Tokenizer:
    tok = Tokenizer(models.BPE())
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tok.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(
        vocab_size=vocab_size,
        special_tokens=SPECIAL,
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
        min_frequency=2,
        show_progress=False,
    )
    tok.train_from_iterator(texts, trainer=trainer)
    TOKENIZER_PATH.parent.mkdir(parents=True, exist_ok=True)
    tok.save(str(TOKENIZER_PATH))
    return tok


_cached: Tokenizer | None = None


def load() -> Tokenizer | None:
    global _cached
    if _cached is None and TOKENIZER_PATH.exists():
        _cached = Tokenizer.from_file(str(TOKENIZER_PATH))
    return _cached


def exists() -> bool:
    return TOKENIZER_PATH.exists()


def sid(tok: Tokenizer, token: str) -> int:
    return tok.token_to_id(token)


def encode_chat(tok: Tokenizer, messages: list[dict], memory: str = "") -> list[int]:
    """Turn a conversation into ids. The trailing assistant tag primes a reply."""
    ids: list[int] = []
    if memory:
        ids += [sid(tok, MEM_OPEN)] + tok.encode(memory).ids + [sid(tok, MEM_CLOSE)]
    tags = {"user": USER, "assistant": ASSISTANT, "system": SYSTEM}
    for m in messages:
        ids += [sid(tok, tags.get(m["role"], USER))] + tok.encode(m["content"]).ids + [sid(tok, END)]
    return ids


def chat_training_ids(tok: Tokenizer, messages: list[dict]) -> list[int]:
    return encode_chat(tok, messages) + [sid(tok, EOT)]
