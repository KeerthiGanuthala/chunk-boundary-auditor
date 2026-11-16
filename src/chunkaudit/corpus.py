"""Seeded corpus generator: documents with planted facts and the spans each fact needs.

The corpus exists because a public dataset cannot tell you which facts it contains, so it cannot
tell you which ones a chunker lost. Here every fact is planted on purpose, with the exact text
spans a reader needs to answer its question, so the audit can ask a precise question of every chunk:
did all of those spans land together?

Five kinds of fact are planted, in increasing order of how badly a boundary hurts them:

    single           subject and value in one sentence
    cross_sentence   the subject is named in one sentence and the value follows in the next,
                     attached by a pronoun, so the value sentence alone names nothing
    cross_paragraph  the same shape across a paragraph break
    cross_page       the same shape across a page break (a footer lands in between)
    table            a header row and a data row; the cell is meaningless without both

Filler sentences carry numbers, units and years of their own, so a matcher cannot find a fact by
looking for "the number" and the fixture is not trivially easy.

Everything is derived from one integer seed through ``random.Random`` so the output is identical on
every machine and every Python version in the CI matrix.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

FACT_KINDS = ("single", "cross_sentence", "cross_paragraph", "cross_page", "table")

_SYLLABLES = ("var", "len", "ost", "bro", "kel", "mir", "dan", "tov", "ril", "sen", "qua", "nex")
_ATTRIBUTES = (
    ("rated output", ("MW", 80, 950)),
    ("service interval", ("months", 6, 36)),
    ("unit price", ("USD", 1200, 98000)),
    ("mass", ("kg", 40, 9800)),
    ("design pressure", ("bar", 4, 320)),
    ("storage capacity", ("TB", 12, 880)),
    ("nominal voltage", ("V", 110, 690)),
    ("warranty period", ("years", 1, 12)),
)
_SITES = ("Ostbro", "Kelmar", "Danvik", "Tovrin", "Rilsen", "Quanex", "Mirvale", "Senholm")
_FILLER = (
    "Operators replaced the inlet filters during the {season} outage.",
    "The schedule slipped by {n} weeks after a late delivery.",
    "A review in {year} found the logbooks complete and legible.",
    "Routine inspection covered {n} access panels on the north face.",
    "Spare parts for the assembly are held at the {site} depot.",
    "The crew logged {n} hours of maintenance in the {season} window.",
    "Vibration readings stayed within the published envelope all year.",
    "A revised procedure was issued in {year} and signed by the shift lead.",
    "The contractor completed {n} weld repairs under supervision.",
    "Cooling water is drawn from the {site} reservoir in summer.",
    "Noise surveys were repeated at {n} points along the fence line.",
    "The {season} report lists {n} open actions, none rated critical.",
    "Training records show {n} staff certified on the new console.",
    "Corrosion on the {site} spur was treated and recoated in {year}.",
)
_SEASONS = ("spring", "summer", "autumn", "winter")


@dataclass(frozen=True)
class Fact:
    """A planted fact and the spans a chunk must contain for the fact to be answerable from it."""

    fact_id: str
    doc_id: str
    kind: str
    question: str
    answer: str
    spans: tuple[str, ...]


@dataclass
class Page:
    """Paragraphs in reading order. A table is a paragraph whose lines are newline separated."""

    paragraphs: list[str] = field(default_factory=list)


@dataclass
class Document:
    doc_id: str
    title: str
    layout: str  # single | two_column | two_column_reversed
    pages: list[Page]
    facts: list[Fact]

    def text(self) -> str:
        """The document as the generator wrote it: pages joined, paragraphs blank-line separated."""
        return "\n\n".join("\n\n".join(p.paragraphs) for p in self.pages)


@dataclass
class Corpus:
    seed: int
    documents: list[Document]

    @property
    def facts(self) -> list[Fact]:
        return [f for d in self.documents for f in d.facts]


class _Namer:
    """Hands out entity names that are unique across the whole corpus."""

    def __init__(self, rng: random.Random):
        self._rng = rng
        self._used: set[str] = set()

    def entity(self) -> str:
        while True:
            stem = "".join(self._rng.choice(_SYLLABLES) for _ in range(2)).capitalize()
            model = f"{self._rng.choice('KMRTVX')}{self._rng.randint(1, 9)}"
            name = f"{stem} {model}"
            if name not in self._used:
                self._used.add(name)
                return name


def _value(rng: random.Random, spec: tuple[str, int, int]) -> str:
    unit, lo, hi = spec
    return f"{rng.randint(lo, hi)} {unit}"


def _filler(rng: random.Random) -> str:
    template = rng.choice(_FILLER)
    return template.format(
        season=rng.choice(_SEASONS),
        n=rng.randint(2, 48),
        year=rng.randint(1991, 2024),
        site=rng.choice(_SITES),
    )


def _paragraph(rng: random.Random, sentences: int) -> list[str]:
    return [_filler(rng) for _ in range(sentences)]


def _single_fact(rng: random.Random, namer: _Namer, doc_id: str, idx: int) -> tuple[Fact, str]:
    entity = namer.entity()
    attr, spec = rng.choice(_ATTRIBUTES)
    value = _value(rng, spec)
    sentence = f"The {entity} unit has a {attr} of {value}."
    fact = Fact(
        fact_id=f"{doc_id}-single-{idx}",
        doc_id=doc_id,
        kind="single",
        question=f"What is the {attr} of the {entity} unit?",
        answer=value,
        spans=(sentence,),
    )
    return fact, sentence


def _pair_fact(
    rng: random.Random, namer: _Namer, doc_id: str, kind: str, idx: int
) -> tuple[Fact, str, str]:
    entity = namer.entity()
    attr, spec = rng.choice(_ATTRIBUTES)
    value = _value(rng, spec)
    site = rng.choice(_SITES)
    year = rng.randint(1988, 2023)
    first = f"The {entity} unit was commissioned at the {site} site in {year}."
    second = f"Its {attr} is {value}."
    fact = Fact(
        fact_id=f"{doc_id}-{kind}-{idx}",
        doc_id=doc_id,
        kind=kind,
        question=f"What is the {attr} of the {entity} unit?",
        answer=value,
        spans=(first, second),
    )
    return fact, first, second


def _table_fact(rng: random.Random, namer: _Namer, doc_id: str, idx: int) -> tuple[Fact, str]:
    cols = rng.sample(_ATTRIBUTES, 2)
    header = "Unit | " + " | ".join(attr for attr, _ in cols)
    rows = []
    target_row = rng.randint(0, 3)
    fact: Fact | None = None
    for r in range(4):
        entity = namer.entity()
        values = [_value(rng, spec) for _, spec in cols]
        line = f"{entity} | " + " | ".join(values)
        rows.append(line)
        if r == target_row:
            col = rng.randint(0, 1)
            fact = Fact(
                fact_id=f"{doc_id}-table-{idx}",
                doc_id=doc_id,
                kind="table",
                question=f"What is the {cols[col][0]} of the {entity} unit?",
                answer=values[col],
                spans=(header, line),
            )
    assert fact is not None
    table = "\n".join([header, *rows])
    return fact, table


def generate_document(
    rng: random.Random,
    namer: _Namer,
    doc_id: str,
    *,
    pages: int,
    layout: str,
    facts_single: int,
    facts_cross_sentence: int,
    facts_cross_paragraph: int,
    facts_cross_page: int,
    facts_table: int,
    paragraphs_per_page: int = 6,
) -> Document:
    """Build one document. Facts are planted into filler so their positions are unpredictable."""
    if facts_cross_page > pages - 1:
        raise ValueError("more cross-page facts than page boundaries")

    # Start from filler pages: a list of paragraphs, each a list of sentences.
    page_paras: list[list[list[str]]] = [
        [_paragraph(rng, rng.randint(3, 5)) for _ in range(paragraphs_per_page)]
        for _ in range(pages)
    ]
    facts: list[Fact] = []

    # cross_page: last sentence of the last paragraph on page p, first sentence on page p+1.
    boundaries = rng.sample(range(pages - 1), facts_cross_page)
    for i, p in enumerate(boundaries):
        fact, first, second = _pair_fact(rng, namer, doc_id, "cross_page", i)
        page_paras[p][-1].append(first)
        page_paras[p + 1][0].insert(0, second)
        facts.append(fact)

    # cross_paragraph: end of paragraph k and start of paragraph k+1 on one page.
    for i in range(facts_cross_paragraph):
        p = rng.randrange(pages)
        k = rng.randrange(paragraphs_per_page - 1)
        fact, first, second = _pair_fact(rng, namer, doc_id, "cross_paragraph", i)
        page_paras[p][k].append(first)
        page_paras[p][k + 1].insert(0, second)
        facts.append(fact)

    # cross_sentence: two adjacent sentences inside one paragraph.
    for i in range(facts_cross_sentence):
        p = rng.randrange(pages)
        k = rng.randrange(paragraphs_per_page)
        fact, first, second = _pair_fact(rng, namer, doc_id, "cross_sentence", i)
        pos = rng.randint(1, max(1, len(page_paras[p][k]) - 1))
        page_paras[p][k][pos:pos] = [first, second]
        facts.append(fact)

    # single: one sentence anywhere.
    for i in range(facts_single):
        p = rng.randrange(pages)
        k = rng.randrange(paragraphs_per_page)
        fact, sentence = _single_fact(rng, namer, doc_id, i)
        pos = rng.randint(0, len(page_paras[p][k]))
        page_paras[p][k].insert(pos, sentence)
        facts.append(fact)

    # Render sentences to paragraph strings, then splice tables in as their own paragraphs.
    rendered: list[Page] = [Page([" ".join(s) for s in paras]) for paras in page_paras]
    # Spread tables over distinct pages where possible so no page carries them all.
    table_pages = [
        rng.sample(range(pages), min(pages, facts_table - k)) for k in range(0, facts_table, pages)
    ]
    table_pages = [p for group in table_pages for p in group]
    for i in range(facts_table):
        p = table_pages[i]
        fact, table = _table_fact(rng, namer, doc_id, i)
        # Never before the first paragraph: a cross_page second span must stay first on its page.
        pos = rng.randint(1, len(rendered[p].paragraphs))
        rendered[p].paragraphs.insert(pos, table)
        facts.append(fact)

    title = f"Asset register {doc_id}: {rng.choice(_SITES)} operations"
    return Document(doc_id=doc_id, title=title, layout=layout, pages=rendered, facts=facts)


def generate_corpus(
    seed: int,
    *,
    documents: int,
    pages_min: int,
    pages_max: int,
    two_column_share: float,
    reversed_stream_share: float,
    facts_single: int,
    facts_cross_sentence: int,
    facts_cross_paragraph: int,
    facts_cross_page: int,
    facts_table: int,
) -> Corpus:
    """Generate the whole corpus from one seed. Same arguments, same bytes, any machine."""
    rng = random.Random(seed)
    namer = _Namer(rng)
    docs: list[Document] = []
    two_col_count = round(documents * two_column_share)
    reversed_count = round(two_col_count * reversed_stream_share)
    layouts = (
        ["two_column_reversed"] * reversed_count
        + ["two_column"] * (two_col_count - reversed_count)
        + ["single"] * (documents - two_col_count)
    )
    rng.shuffle(layouts)
    for n in range(documents):
        doc_id = f"D{n + 1:02d}"
        docs.append(
            generate_document(
                rng,
                namer,
                doc_id,
                pages=rng.randint(pages_min, pages_max),
                layout=layouts[n],
                facts_single=facts_single,
                facts_cross_sentence=facts_cross_sentence,
                facts_cross_paragraph=facts_cross_paragraph,
                facts_cross_page=facts_cross_page,
                facts_table=facts_table,
            )
        )
    return Corpus(seed=seed, documents=docs)


def corpus_from_policy(policy) -> Corpus:
    """Convenience: generate from a ``Policy`` (see ``config.load_policy``)."""
    fx = policy.fixture
    return generate_corpus(
        fx.seed,
        documents=fx.documents,
        pages_min=fx.pages_min,
        pages_max=fx.pages_max,
        two_column_share=fx.two_column_share,
        reversed_stream_share=fx.reversed_stream_share,
        facts_single=fx.facts_single,
        facts_cross_sentence=fx.facts_cross_sentence,
        facts_cross_paragraph=fx.facts_cross_paragraph,
        facts_cross_page=fx.facts_cross_page,
        facts_table=fx.facts_table,
    )
