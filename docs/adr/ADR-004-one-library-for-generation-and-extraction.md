# ADR-004: One library for generating the fixture and extracting it

Status: accepted, with the risk it carries stated.

## Context

The fixture PDFs are written with PyMuPDF and read back with PyMuPDF. A library reading its own
output is a round trip that can be cleaner than reality: the producer's block structure, font
metrics and stream order are exactly what the consumer expects. An audit that only ever saw clean
round trips would measure the chunker on text no production pipeline receives.

## Decision

Keep one library, because it is the one on the candidate's resume and the one most RAG pipelines
in this stack use for ingestion, and defeat the clean round trip on purpose:

- half the documents are two-column, which position-sorted extraction interleaves line by line;
- of the 9 two-column documents, 4 write the right column into the content stream first, which
  makes raw stream order wrong even though the page looks identical;
- every page carries a footer, so a cross-page fact always has a footer between its two spans;
- every paragraph is its own text box, which is how most document producers behave and what makes
  the block-clustering extraction mode possible and necessary.

The alternative, generating with a second library, was rejected because it would add a dependency
whose own quirks would need explaining, without removing the need for the adversarial layouts.

## Consequences

- The extraction experiment measures a real failure (sort=True breaks 122 of the 396 facts, every
  one of them on a two-column page) rather than a round-trip artefact.
- What it does not measure: scanned pages, hyphenation at line ends, rotated text, forms, and
  producers whose block structure PyMuPDF segments differently. Each of those is a layout the
  fixture does not contain, and a loss it therefore cannot see.
