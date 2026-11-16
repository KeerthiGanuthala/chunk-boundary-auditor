# ADR-002: Containment as the metric, and splitters reimplemented rather than imported

Status: accepted.

## Context

A chunking strategy is usually judged by running retrieval over the chunks and scoring the
answers. That measures the whole pipeline at once: embedding model, index, retriever, reranker,
prompt and chunker. When the score moves, nothing in it says which of those moved it.

## Decision

Judge the chunker on one question it alone controls: for each planted fact, does at least one
chunk contain every span the fact needs? Three outcomes, in order of precedence:

1. broken: a span is missing from the extracted text, so extraction lost it and no chunker could
   have contained it;
2. contained: some chunk holds every span;
3. orphaned: every span survived extraction and no single chunk holds all of them.

Matching is on whitespace-normalised text, because extraction wraps lines and chunkers cut on
tokens. The order of spans inside a chunk is not required: a reader can resolve "Its rated output"
when the unit is named two lines later on the same screen, and refusing that would overcount.

A fact that could be answered by stitching two adjacent chunks together is counted as orphaned.
Retrievers return chunks, not neighbourhoods, and a pipeline that fetches neighbours is a different
pipeline, which can be audited by chunking with that neighbourhood as the unit.

The chunkers themselves are reimplemented in this repository in a few dozen lines each: fixed
windows, recursive separator splitting, sentence packing, page-aware windows and paragraph packing.
Importing them from a framework was rejected because a framework splitter changes its boundary
rules between versions and the audit has to be able to say exactly where a boundary fell and why.
The recursive strategy keeps the framework's separator order on purpose, including a single
newline as the second separator, because that is what production pipelines run on extracted PDF
text; the sentence strategy unwraps single newlines first, and the README's war story records why
that distinction exists.

## Consequences

- The metric is strict and monotone: more context can only move a fact from orphaned to
  contained, never the other way, which is what makes the size sweep readable.
- It is also blind to everything after containment. The README's "what this cannot measure"
  section says so.
- 5 strategies and 3 extraction orders are enough to answer the README's questions; adding a
  strategy is one function and one policy line.
