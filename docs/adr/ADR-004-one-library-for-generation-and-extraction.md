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
- Raw PDF bytes are not reproducible across PyMuPDF versions, and were never the invariant worth
  pinning. The committed fixture was frozen under PyMuPDF 2.1 (Python 3.11 and up); Python 3.10
  resolves to 1.28.2, the newest wheel it has, and 1.28.2 writes the same corpus to different
  compressed bytes. The extracted text, and therefore every audit figure, is identical under both.
  So the fixture is checked by content (`chunkaudit generate --check` compares the facts and the
  extracted text) and the committed bytes are pinned by SHA-256 only to catch tampering and
  corruption of the committed files, not as a cross-environment guarantee. An early version checked
  bytes and failed CI on Python 3.10 for a difference that moved no number; the test suite now pins
  that a bytes-only difference passes and a text difference fails.
