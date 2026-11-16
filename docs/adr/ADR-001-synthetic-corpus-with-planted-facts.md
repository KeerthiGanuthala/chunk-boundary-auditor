# ADR-001: A seeded synthetic corpus with planted facts, not a public dataset

Status: accepted. This is the boundary ADR: it states what the repository can and cannot establish.

## Context

The question the tool answers is "which facts did this chunking strategy make unretrievable". To
answer it, the tool has to know every fact a document contains and exactly which text a reader
needs to answer it. No public document collection carries that information. A QA dataset over PDFs
gives questions and answers, but not the set of spans that must co-occur in a chunk, and it never
tells you about the facts nobody wrote a question for.

## Decision

Generate the corpus from one seed. Every document is filler prose with facts planted on purpose,
each recorded with the spans a reader needs: one sentence for a single fact, two for the
cross-sentence, cross-paragraph and cross-page kinds, and a header line plus a row line for a
table fact. The committed fixture holds 18 PDFs with 396 planted facts, of which 108 single,
108 cross-sentence, 72 cross-paragraph, 36 cross-page and 72 table.

The alternative, a public corpus with a handful of hand-labelled facts, was rejected because the
labelling effort scales with the corpus and the unlabelled facts are exactly the ones a boundary
loses without anyone noticing.

## What this can establish

- Whether a chunking strategy keeps a fact's spans together, by kind and by size, with an exact
  count and no sampling error: every planted fact is checked, so a measured zero is a zero over
  the whole fixture, with a resolution floor of one in 396 for any claim about the population of
  facts this fixture stands in for.
- Whether a PDF extraction order loses a span before any chunker runs, attributable to the layout
  that caused it, because the layout of every document is known.
- The direction and the size of the effect of overlap, size and strategy relative to each other.

## What this cannot establish

- Retrieval quality. Containment is necessary for retrieval, not sufficient. A chunk that holds
  the spans still has to outrank its neighbours for a query, and this repository never runs a
  retriever (ADR-002 says why).
- Absolute loss rates on real documents. The filler prose is regular, the sentences are short, and
  facts are planted at a density no real report has. The counts here are comparable with each
  other and with nothing outside this fixture. The one claim that genuinely needs real documents
  is "a strategy that loses 1.3 percent of the planted facts here loses about that much in
  production", and it is not made anywhere in this repository.
- Anything about tokenizers other than the repository's own (ADR-003).

## Consequences

Every number in the README is reproducible from one command with no network and no key. The
price is the paragraph above: a reviewer who wants a production loss rate has to plant facts in
their own documents, which the corpus module is written to make easy, and which is listed as the
first item of future work.
