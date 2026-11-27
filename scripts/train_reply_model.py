"""Fit the small in-browser English reply-intent classifier on fictional labelled text."""

import hashlib
import json
import math
import random
import re
from collections import Counter
from pathlib import Path


DATA = Path(__file__).resolve().parents[1] / "invoice_review" / "data"
LABELS = ["approve", "decline", "conditional", "question", "uncertain"]
# General language patterns pool evidence across rare forms. Their influence
# on each class is learned alongside ordinary words and word pairs.
CUE_GROUPS = {
    "qualification": ["if", "unless", "provided", "providing", "assuming", "pending",
                      "subject to", "as long as", "once", "on condition", "proviso",
                      "depends on", "conditional", "until", "contingent"],
    "negation": ["not", "cannot", "never", "neither"],
    "indecision": ["not sure", "undecided", "possibly", "maybe", "might", "uncertain"],
    "request": ["?", "please quote", "please price", "please tell", "could you"],
}


def tokens(text):
    # Keep this feature contract in sync with demo/reply-intent.js.
    cleaned = text.lower().replace("’", "'").replace("won't", "will not").replace("can't", "cannot")
    cleaned = cleaned.replace("n't", " not").replace("'ll", " will").replace("'re", " are")
    cleaned = re.sub(r"(?:aud\s*|\$\s*)[\d,.]+|\b\d+(?:[,.]\d+)*\b", " amount ", cleaned)
    return re.findall(r"[a-z]+|\?", cleaned)


def features(text):
    words = tokens(text)
    result = {"w:" + word for word in words}
    result.update("b:" + first + "/" + second for first, second in zip(words, words[1:]))
    result.update("p:" + word[:5] for word in words if len(word) >= 6)
    sentence = " " + " ".join(words) + " "
    result.update("c:" + name for name, phrases in CUE_GROUPS.items()
                  if any(" " + phrase + " " in sentence for phrase in phrases))
    return sorted(result)


def distribution(scores):
    maximum = max(scores)
    exps = [math.exp(score - maximum) for score in scores]
    total = sum(exps)
    return [value / total for value in exps]


def fit(training):
    samples = []
    counts = Counter()
    # Reuse each fictional job across all five intents so a site, day or
    # price repeated in a sentence cannot stand in for the sender's decision.
    matched = training["matched_examples"]
    for label_index, label in enumerate(LABELS):
        examples = training[label] + [frame.format(job=job)
                                      for frame in matched["frames"][label]
                                      for job in matched["jobs"]]
        for sentence in examples:
            terms = features(sentence)
            counts.update(terms)
            samples.append((terms, label_index))
    # One-off phrases give a misleadingly perfect fit without vocabulary reuse.
    vocab = sorted(k for k, n in counts.items() if n >= 2)
    weights = {k: [0.0] * len(LABELS) for k in vocab}
    rows = [([k for k in terms if k in weights], target) for terms, target in samples]
    bias = [0.0] * len(LABELS)
    rng = random.Random(3701)
    for epoch in range(180):
        rng.shuffle(rows)
        rate = 0.15 / math.sqrt(1 + epoch / 20)
        for terms, target in rows:
            scores = bias.copy()
            for term in terms:
                for i, value in enumerate(weights[term]):
                    scores[i] += value
            probs = distribution(scores)
            for i, prob in enumerate(probs):
                change = rate * (int(i == target) - prob)
                bias[i] += change
                for term in terms:
                    weights[term][i] += change
        # L2 shrinkage on the word and phrase weights only.
        for w in weights.values():
            for i in range(len(w)):
                w[i] *= 0.993
    return {"schema": 1, "method": "multinomial logistic regression on binary word, prefix, bigram and linguistic features",
            "cue_groups": CUE_GROUPS,
            "labels": LABELS, "training_count": len(samples),
            "bias": [round(value, 5) for value in bias],
            "weights": {term: [round(value, 5) for value in weights[term]] for term in vocab}}


def main():
    training = json.loads((DATA / "reply_training.json").read_text(encoding="utf-8"))
    model = fit(training)
    canonical = json.dumps(training, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    model["training_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    path = DATA / "reply_model.json"
    path.write_text(json.dumps(model, separators=(",", ":"), ensure_ascii=True) + "\n",
                    encoding="utf-8", newline="\n")
    print(f"Trained on {model['training_count']} fictional replies; {len(model['weights'])} reusable features.")


if __name__ == "__main__":
    main()
