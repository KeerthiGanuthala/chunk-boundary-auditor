# ADR-005: Overlap is a priced trade, published as cost against benefit

Status: accepted.

## Context

The standard answer to "a boundary split my fact" is overlap: repeat the tail of each chunk at the
head of the next. Overlap is almost always quoted as a benefit without a cost, and the cost is real:
every overlapping token is embedded, stored and ranked again, and the index grows.

## Decision

Measure overlap as two numbers side by side, facts recovered and chunk growth, and publish both
every time either is mentioned. The second experiment sweeps overlap for the two strategies that
take a token overlap. For fixed windows at the policy size, an overlap of 64 tokens recovers every
orphan at 13 percent more chunks. For the recursive splitter the same sweep found something the
README leads with: 32 tokens of overlap lost 1 more fact than no overlap at all, and 64 tokens lost
4 more, because the carried pieces consume room in the next chunk and push a paragraph pair apart
that used to fit; it reaches zero at 256 tokens of overlap, which is half the chunk, with the index 61 percent larger.

The alternative, recommending a single overlap value, was rejected because the right value depends
on the strategy and the unit it carries, and the recursive result shows the sign can flip.

## Consequences

- The README never says "use overlap". It says what each overlap recovered and what it cost on this
  fixture, and that the recursive result is the reason to measure rather than assume.
- The same two-column shape, cost against benefit, is used for extraction mode: block clustering
  loses 0 of the facts and costs one extra sort per page.
