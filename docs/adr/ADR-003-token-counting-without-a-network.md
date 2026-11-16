# ADR-003: Token counting without a network

Status: accepted. This is the boring choice, recorded because it looks like a shortcut.

## Context

Chunk sizes are quoted in tokens, and the usual tokenizer downloads its vocabulary the first time
it is imported. This repository promises that every figure reproduces from a fresh clone with no
network. A tokenizer that phones home on first use breaks that promise on exactly the machine a
reviewer uses: a clean one.

## Decision

Count tokens with a fixed rule: a word or a punctuation mark is one token, and an alphabetic word
longer than four characters is split into four-character pieces to approximate subword
tokenization. The same function returns character offsets so fixed windows cut between tokens.
The rule is deterministic across Python versions and machines, has no dependency and no state.

The alternative, a real BPE tokenizer behind an optional extra, was rejected for the default path
and is listed as future work, because a size of 512 tokens would then mean one thing on a machine
with the extra installed and another without it, and the number checker could not tell which the
README was describing.

## Consequences

- A size of 512 in this repository is 512 of its own tokens. It is comparable with every other
  size in this repository and with no size quoted anywhere else. The README says so next to the
  first size it quotes.
- The size sweep still answers its question, because the question is about the shape of the loss
  as the window shrinks, not about where 512 BPE tokens falls on it.
- The fixed strategy cuts between tokens, which for a pieced word means inside the word, as a real
  token splitter does. The test suite pins that this is intended.
