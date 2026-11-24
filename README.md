# voi

Experiments toward simulating a society of agents and putting its representatives behind a veil of ignorance to redesign it.

## Convention pilot

`pilot/` is a small harness for one question: when delegates choose among concrete economic plans, how much does what they know about their own position change the choice?

Twelve delegates choose among four plans, or keeping today's arrangements, over three rounds: a first ranking made alone, a second after hearing everyone's statements, and a binding vote. A plan needs 9 of 12 first-place votes; otherwise today's arrangements continue. Every delegate is told to get the best outcome for their own household. The three conditions differ only in the "Your situation" paragraph of the briefing:

| Condition | What a delegate knows |
|---|---|
| `known` | Their own occupation, household and income group |
| `lottery` | Nothing about themselves; a fair draw will place them, one chance in five per group |
| `withheld` | Nothing about themselves, and no basis for estimating the odds |

The plans are built so that different decision rules pick different plans:

| Rule | Picks |
|---|---|
| Highest average income | Cedar |
| Average income, with moderate aversion to risk | Alder |
| Highest income for the lowest group | Hazel |
| Smallest gap between top and bottom | Birch |
| Own group's income | Hazel (lowest fifth), Birch (second fifth), Cedar (middle, fourth and top fifths) |

Everything a delegate reads is in `pilot/materials/`. The society description and the plan numbers are hand-written and stylized, loosely modelled on the United States. They are not sourced figures.

### Running it

The harness makes no model calls. It writes one prompt file per delegate under an opaque id, expects one JSON reply beside it, and does the bookkeeping.

```bash
python3 pilot/convention.py build   --run runs/NAME --round 1 --dispatch DIR
```

Run a model on each `DIR/<id>.prompt.md` and have it write `DIR/<id>.reply.json`. The instruction used for that is `AGENT_INSTRUCTION` in `pilot/convention.py`.

```bash
python3 pilot/convention.py collect --run runs/NAME --round 1 --dispatch DIR
```

Repeat `build` and `collect` for rounds 2 and 3; each round's prompt includes the earlier statements, straw polls and the delegate's own record. Add `--conditions known` to `build` to run a subset.

```bash
python3 pilot/convention.py tally --run runs/NAME
```

This writes `report.md` and `results.json` in the run directory.

```bash
python3 pilot/convention.py selftest
```

This runs all three rounds with random replies to check the plumbing.

### What the pilot does not cover

- Delegates choose from a fixed menu and are told to treat the projections as accurate. They do not draft institutions or argue about the economics.
- Rights and mobility are held equal across plans, so only the income distribution is at stake.
- Behind either veil all twelve delegates receive the same briefing, apart from the order in which the plans are listed.
- Each run is a single convention per condition, with no replication.

## Runs

- `runs/pilot-01/`: first run. See `report.md` for results and `NOTES.md` for how it was run.
