import re

_STOPWORDS = {
    "pos","ach","debit","credit","card","purchase","payment","pmt","online","web","www",
    "inc","llc","co","company","corp","corporation","the",
}

def merchant_key(description: str) -> str:
    s = (description or "").lower().strip()
    # drop common prefixes like "sq *", "tst*", etc (tune later)
    s = re.sub(r"[^a-z0-9\s\*]", " ", s)
    s = re.sub(r"\d+", " ", s)
    s = s.replace("*", " ")
    s = re.sub(r"\s+", " ", s).strip()

    tokens = [t for t in s.split(" ") if t and t not in _STOPWORDS]
    # keep first N tokens to avoid overfitting to long tails
    tokens = tokens[:6]
    return " ".join(tokens)


def canonical_merchant_name(description: str) -> str:
    key = merchant_key(description)
    if not key:
        return (description or "").strip() or "Unknown"
    return " ".join(word.capitalize() for word in key.split(" "))
