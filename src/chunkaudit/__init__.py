"""chunk-boundary-auditor: measures which planted facts a chunking strategy makes unretrievable.

The package is organised as a pipeline whose stages can each be blamed separately:

    corpus.py    plants facts in synthetic documents and records which spans each fact needs
    pdfgen.py    renders those documents to PDF with PyMuPDF, in the layouts that hurt
    extract.py   pulls text back out of the PDFs, in the three orders PyMuPDF can give you
    tokens.py    counts tokens deterministically so chunk sizes mean the same thing on every machine
    chunkers.py  the five chunking strategies under test
    audit.py     decides, per fact and per chunk, whether every span the fact needs landed together
    report.py    turns the audit into tables, JSON and an exit code

Nothing here calls the network or an embedding model. Every figure is a count over a committed,
seeded fixture.
"""

__version__ = "0.1.0"
