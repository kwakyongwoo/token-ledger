"""API list prices in USD per million tokens, used to estimate cost per request."""
from __future__ import annotations

PRICES_DATE = "2026-11-03"  # claude-api skill model table; update here when prices change

# model prefix: (input, output, cache_read). Cache writes are 1.25x input (5m TTL) and 2x input (1h TTL).
PRICES = {
    "claude-fable-5-2": (8.0, 40.0, 0.20),
    "claude-mythos-5-2": (8.0, 40.0, 0.20),
    "claude-fable-5-1": (10.0, 50.0, 0.25),
    "claude-mythos-5-1": (10.0, 50.0, 0.25),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0, 0.50),
    "claude-opus-4-8": (5.0, 25.0, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0, 0.10),
    "claude-sonnet-5": (2.0, 10.0, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-haiku-4-5": (1.0, 5.0, 0.10),
}
# Haiku 5.5 charges more when the prompt is over 100K tokens.
HAIKU_55_LONG = (0.50, 2.50, 0.05)


def _base(model: str):
    keys = [k for k in PRICES if model.startswith(k)]
    return PRICES[max(keys, key=len)] if keys else None


def request_cost(model: str | None, usage: dict) -> float | None:
    """Cost of one API request, or None when the model has no known price."""
    price = _base(model or "")
    if price is None:
        return None
    inp = usage.get("input_tokens") or 0
    out = usage.get("output_tokens") or 0
    read = usage.get("cache_read_input_tokens") or 0
    write = usage.get("cache_creation_input_tokens") or 0
    split = usage.get("cache_creation") or {}
    w1h = split.get("ephemeral_1h_input_tokens") or 0
    w5m = (split.get("ephemeral_5m_input_tokens") or 0) if split else write  # no split: assume the 5-minute TTL
    if (model or "").startswith("claude-haiku-5-5") and inp + read + write > 100_000:
        price = HAIKU_55_LONG
    p_in, p_out, p_read = price
    cost = (inp * p_in + out * p_out + read * p_read + w5m * p_in * 1.25 + w1h * p_in * 2) / 1e6
    # shortcut: fast mode is billed at 2x on the models that offer it; cache rates assumed to scale the same.
    return cost * 2 if usage.get("speed") == "fast" else cost
