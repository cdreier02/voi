#!/usr/bin/env python3
"""Convention pilot: build delegate prompts, collect replies, tally results.

No model calls are made here. `build` writes one prompt file per delegate into
a dispatch directory under an opaque id; whatever runs the model writes one
JSON reply next to it; `collect` validates the replies and files them under the
run directory; `tally` writes the report.

    python3 pilot/convention.py build   --run runs/pilot-01 --round 1 --dispatch DIR
    python3 pilot/convention.py collect --run runs/pilot-01 --round 1 --dispatch DIR
    python3 pilot/convention.py tally   --run runs/pilot-01
    python3 pilot/convention.py selftest
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

MATERIALS = Path(__file__).resolve().parent / "materials"

CONDITIONS = ("known", "lottery", "withheld")
CONDITION_LABELS = {
    "known": "Position known",
    "lottery": "Lottery (equal odds)",
    "withheld": "Position withheld (no odds)",
}
N_ROUNDS = 3
QUORUM = 9

# Three base orders, each rotated four ways: across the twelve delegates every
# plan appears in every table position exactly three times.
BASE_ORDERS = ([0, 1, 2, 3], [2, 0, 3, 1], [1, 3, 0, 2])

THIS_ROUND = {
    1: "This is round 1. No delegate has spoken yet. Give your ranking as it stands now, your private note, and your statement to the convention.",
    2: "This is round 2. You have now heard every delegate's round 1 statement and the straw poll. Give your ranking as it stands now, your private note, and your statement to the convention. You may hold your position or change it.",
    3: "This is round 3, the final vote. The plan you rank first is your binding vote. Give your final ranking, your private note, and a closing statement.",
}

# The instruction given to whatever runs the model on one prompt file.
AGENT_INSTRUCTION = (
    "Read the file {prompt} in full. It gives you a role in a role-play exercise and "
    "instructions for your answer; follow them exactly and answer fully in character. "
    "Write your answer to {reply} as a single JSON object in the format the file "
    "specifies, with nothing else in the file. Do not read, list, or search for any "
    "other files, and do not run any other commands. When the file is written, reply "
    "with only the word DONE."
)

# Vocabulary that signals a delegate is reciting political philosophy.
THEORY_TERMS = (
    r"rawls\w*", r"veil", r"original position", r"difference principle", r"maximin",
    r"harsanyi", r"least[- ]advantaged", r"utilitarian\w*", r"insufficient reason",
)


class Materials:
    def __init__(self) -> None:
        plans = json.loads((MATERIALS / "plans.json").read_text())
        self.groups: list[str] = plans["groups"]
        self.today: dict = plans["today"]
        self.plans: list[dict] = plans["plans"]
        self.roster = {r["delegate"]: r for r in json.loads((MATERIALS / "roster.json").read_text())}
        self.situations: dict = json.loads((MATERIALS / "situations.json").read_text())
        self.society = (MATERIALS / "society.md").read_text().strip()
        self.briefing = (MATERIALS / "briefing.md").read_text()
        self.delegates = sorted(self.roster)
        self.options = [p["name"] for p in self.plans] + [self.today["name"]]
        self.incomes = {p["name"]: p["incomes"] for p in self.plans + [self.today]}
        self.keys = {p["name"]: p["key"] for p in self.plans}

    def plan_order(self, delegate: int) -> list[dict]:
        i = self.delegates.index(delegate)
        base = BASE_ORDERS[(i // 4) % len(BASE_ORDERS)]
        rot = i % 4
        return [self.plans[j] for j in base[rot:] + base[:rot]]

    def best_for_group(self, group: int) -> set[str]:
        top = max(inc[group] for inc in self.incomes.values())
        return {name for name, inc in self.incomes.items() if inc[group] == top}


def fill(template: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        template = template.replace(f"[[{key}]]", value)
    left = re.findall(r"\[\[\w+\]\]", template)
    if left:
        raise ValueError(f"unfilled placeholders: {left}")
    return template


def render_table(m: Materials, order: list[dict]) -> str:
    def row(entry: dict) -> str:
        inc = entry["incomes"]
        return f"| {entry['name']} | " + " | ".join(str(x) for x in inc) + f" | {round(sum(inc) / len(inc))} |"

    head = "| | " + " | ".join(m.groups) + " | Average |"
    rule = "|---|" + "---|" * (len(m.groups) + 1)
    return "\n".join([head, rule, row(m.today)] + [row(p) for p in order])


def straw_poll(replies: dict[int, dict], options: list[str]) -> str:
    counts = Counter(r["ranking"][0] for r in replies.values())
    ordered = sorted(options, key=lambda o: (-counts[o], o))
    return ", ".join(f"{o} {counts[o]}" for o in ordered)


def render_history(m: Materials, delegate: int, rnd: int, prior: dict[int, dict[int, dict]]) -> str:
    """prior[k][d] is delegate d's reply in round k, for every k < rnd."""
    if rnd == 1:
        return ""
    out = ["", "## The convention so far", ""]
    for k in range(1, rnd):
        out += [f"### Round {k} statements", ""]
        for d in m.delegates:
            out += [f"Delegate {d}: \"{prior[k][d]['statement'].strip()}\"", ""]
        out += [f"Straw poll after round {k} (first choices): {straw_poll(prior[k], m.options)}.", ""]
    out += ["## Your own record", ""]
    for k in range(1, rnd):
        mine = prior[k][delegate]
        out += [f"Round {k}: you ranked {' > '.join(mine['ranking'])}. Your private note: \"{mine['private_note'].strip()}\"", ""]
    return "\n".join(out)


def build_prompt(m: Materials, cond: str, delegate: int, rnd: int, prior: dict) -> str:
    order = m.plan_order(delegate)
    card = m.roster[delegate]
    situation = fill(m.situations[cond], {"card": card["card"], "group": m.groups[card["group"]].lower()}) \
        if cond == "known" else m.situations[cond]
    return fill(m.briefing, {
        "delegate": str(delegate),
        "society": m.society,
        "table": render_table(m, order),
        "descriptions": "\n".join(f"- **{p['name']}.** {p['description']}" for p in order),
        "situation": situation,
        "history": render_history(m, delegate, rnd, prior),
        "this_round": THIS_ROUND[rnd],
        "names": ", ".join(sorted(m.options)),
    })


def opaque_id(run_name: str, cond: str, rnd: int, delegate: int) -> str:
    return hashlib.sha256(f"{run_name}|{cond}|{rnd}|{delegate}".encode()).hexdigest()[:10]


def reply_path(run: Path, cond: str, rnd: int, delegate: int) -> Path:
    return run / f"r{rnd}" / cond / f"d{delegate:02d}.reply.json"


def load_round(m: Materials, run: Path, cond: str, rnd: int) -> dict[int, dict]:
    out = {}
    for d in m.delegates:
        p = reply_path(run, cond, rnd, d)
        if p.exists():
            out[d] = json.loads(p.read_text())
    return out


def parse_reply(text: str, options: list[str]) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\s*|\s*```$", "", text).strip()
    obj = json.loads(text)
    canon = {o.lower(): o for o in options}
    ranking = [canon.get(str(x).strip().lower()) for x in obj["ranking"]]
    if sorted(str(x) for x in ranking) != sorted(options):
        raise ValueError(f"ranking is not a permutation of {sorted(options)}: {obj['ranking']}")
    note, statement = obj["private_note"], obj["statement"]
    if not (isinstance(note, str) and isinstance(statement, str) and statement.strip()):
        raise ValueError("private_note and statement must be text, and statement must not be empty")
    return {"ranking": ranking, "private_note": note.strip(), "statement": statement.strip()}


def cmd_build(args) -> int:
    m = Materials()
    run, dispatch = Path(args.run), Path(args.dispatch)
    dispatch.mkdir(parents=True, exist_ok=True)
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    jobs = []
    for cond in args.conditions:
        prior = {k: load_round(m, run, cond, k) for k in range(1, args.round)}
        for k, got in prior.items():
            if len(got) != len(m.delegates):
                print(f"round {k} of '{cond}' is incomplete ({len(got)}/{len(m.delegates)}); collect it first", file=sys.stderr)
                return 1
        for d in m.delegates:
            oid = opaque_id(run.name, cond, args.round, d)
            text = build_prompt(m, cond, d, args.round, prior)
            archive = run / f"r{args.round}" / cond / f"d{d:02d}.prompt.md"
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_text(text)
            prompt = (dispatch / f"{oid}.prompt.md").resolve()
            prompt.write_text(text)
            manifest[oid] = {"condition": cond, "round": args.round, "delegate": d,
                             "plan_order": [p["name"] for p in m.plan_order(d)]}
            jobs.append({"id": oid, "condition": cond, "delegate": d, "prompt": str(prompt),
                         "reply": str(prompt.with_name(f"{oid}.reply.json"))})
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    for job in jobs:
        print(json.dumps(job))
    return 0


def cmd_collect(args) -> int:
    m = Materials()
    run, dispatch = Path(args.run), Path(args.dispatch)
    manifest = json.loads((run / "manifest.json").read_text())
    problems = 0
    for oid, e in sorted(manifest.items(), key=lambda kv: (kv[1]["condition"], kv[1]["delegate"])):
        if e["round"] != args.round:
            continue
        src = dispatch / f"{oid}.reply.json"
        tag = f"{e['condition']} d{e['delegate']:02d} ({oid})"
        if not src.exists():
            print(f"MISSING  {tag}")
            problems += 1
            continue
        try:
            reply = parse_reply(src.read_text(), m.options)
        except (ValueError, KeyError, TypeError) as err:
            print(f"INVALID  {tag}: {err}")
            problems += 1
            continue
        for field, limit in (("private_note", 110), ("statement", 190)):
            words = len(reply[field].split())
            if words > limit:
                print(f"LONG     {tag}: {field} is {words} words")
        dest = reply_path(run, e["condition"], e["round"], e["delegate"])
        dest.write_text(json.dumps(reply, indent=1) + "\n")
    print(f"round {args.round}: {problems} problem(s)")
    return 1 if problems else 0


def theory_hits(text: str) -> list[str]:
    return sorted({hit.lower() for term in THEORY_TERMS for hit in re.findall(rf"\b{term}\b", text, re.I)})


def cmd_tally(args) -> int:
    m = Materials()
    run = Path(args.run)
    data = {c: {k: load_round(m, run, c, k) for k in range(1, N_ROUNDS + 1)} for c in CONDITIONS}
    rounds = {c: [k for k in data[c] if data[c][k]] for c in CONDITIONS}
    results: dict = {"conditions": {}}
    md = [f"# Convention pilot: {run.name}", ""]

    md += ["## First choices by round", "",
           "| Condition | Round | " + " | ".join(m.options) + " | n |", "|---|---|" + "---|" * (len(m.options) + 1)]
    for c in CONDITIONS:
        res = results["conditions"][c] = {"first_choices": {}, "outcome": None}
        for k in rounds[c]:
            counts = Counter(r["ranking"][0] for r in data[c][k].values())
            res["first_choices"][k] = {o: counts[o] for o in m.options}
            md.append(f"| {CONDITION_LABELS[c]} | {k} | " + " | ".join(str(counts[o]) for o in m.options) + f" | {len(data[c][k])} |")
    md.append("")

    md += [f"## Outcome of the final vote ({QUORUM} of {len(m.delegates)} needed)", ""]
    for c in CONDITIONS:
        final = data[c][N_ROUNDS]
        if len(final) < len(m.delegates):
            if rounds[c]:
                k = rounds[c][-1]
                lead, n = Counter(r["ranking"][0] for r in data[c][k].values()).most_common(1)[0]
                md.append(f"- {CONDITION_LABELS[c]}: final vote not held. Round {k} first choices: {lead} {n} of {len(data[c][k])}.")
            else:
                md.append(f"- {CONDITION_LABELS[c]}: no replies.")
            continue
        counts = Counter(r["ranking"][0] for r in final.values())
        winner = next((p["name"] for p in m.plans if counts[p["name"]] >= QUORUM), None)
        results["conditions"][c]["outcome"] = winner or "fails"
        md.append(f"- {CONDITION_LABELS[c]}: " + (f"**{winner}** adopted ({counts[winner]} votes)." if winner
                  else "**no plan adopted**; today's arrangements continue."))
    md.append("")

    md += ["## Average rank in the latest round (1 = best)", "",
           "| Condition | Round | " + " | ".join(m.options) + " |", "|---|---|" + "---|" * len(m.options)]
    for c in CONDITIONS:
        if not rounds[c]:
            continue
        k = rounds[c][-1]
        means = {o: sum(r["ranking"].index(o) + 1 for r in data[c][k].values()) / len(data[c][k]) for o in m.options}
        results["conditions"][c]["mean_rank"] = means
        md.append(f"| {CONDITION_LABELS[c]} | {k} | " + " | ".join(f"{means[o]:.2f}" for o in m.options) + " |")
    md.append("")

    md += ["## Delegates who changed first choice", "", "| Condition | Round 1 to 2 | Round 2 to 3 |", "|---|---|---|"]
    for c in CONDITIONS:
        cells = []
        for a, b in ((1, 2), (2, 3)):
            both = [d for d in m.delegates if d in data[c][a] and d in data[c][b]]
            moved = [d for d in both if data[c][a][d]["ranking"][0] != data[c][b][d]["ranking"][0]]
            cells.append(f"{len(moved)} of {len(both)}" if both else "n/a")
        md.append(f"| {CONDITION_LABELS[c]} | {cells[0]} | {cells[1]} |")
    md.append("")

    md += ["## Position known: first choice against own group's best option", "",
           "| Delegate | Group | Best for own group | " + " | ".join(f"Round {k}" for k in rounds["known"]) + " |",
           "|---|---|---|" + "---|" * len(rounds["known"])]
    for d in m.delegates:
        g = m.roster[d]["group"]
        picks = [data["known"][k].get(d, {}).get("ranking", ["-"])[0] for k in rounds["known"]]
        md.append(f"| {d} | {m.groups[g]} | {', '.join(sorted(m.best_for_group(g)))} | " + " | ".join(picks) + " |")
    md.append("")

    md += ["## Replies using theory vocabulary", "",
           "Counted across all rounds, private note and statement together. Terms: "
           + ", ".join(t.replace(r"\w*", "").replace("[- ]", " ") for t in THEORY_TERMS) + ".", "",
           "| Condition | Replies with a hit | Terms found |", "|---|---|---|"]
    for c in CONDITIONS:
        replies = [r for k in rounds[c] for r in data[c][k].values()]
        hits = [theory_hits(r["private_note"] + " " + r["statement"]) for r in replies]
        terms = Counter(t for h in hits for t in h)
        results["conditions"][c]["theory_vocabulary"] = {"replies": len(replies), "with_hit": sum(bool(h) for h in hits), "terms": dict(terms)}
        md.append(f"| {CONDITION_LABELS[c]} | {sum(bool(h) for h in hits)} of {len(replies)} | "
                  + (", ".join(f"{t} ({n})" for t, n in terms.most_common()) or "none") + " |")
    md.append("")

    md += ["## Private notes", ""]
    for c in CONDITIONS:
        for k in rounds[c]:
            md += [f"### {CONDITION_LABELS[c]}, round {k}", ""]
            for d in m.delegates:
                if d in data[c][k]:
                    r = data[c][k][d]
                    md.append(f"- **D{d}** ({' > '.join(r['ranking'])}): {r['private_note']}")
            md.append("")

    (run / "report.md").write_text("\n".join(md))
    (run / "results.json").write_text(json.dumps(results, indent=1) + "\n")
    print("\n".join(md[: md.index("## Private notes")]))
    return 0


def cmd_selftest(_args) -> int:
    """Run all three rounds with random replies to check the plumbing."""
    m, rng = Materials(), random.Random(0)
    with tempfile.TemporaryDirectory() as tmp:
        run, dispatch = Path(tmp) / "run", Path(tmp) / "dispatch"
        base = argparse.Namespace(run=str(run), dispatch=str(dispatch), conditions=list(CONDITIONS))
        for rnd in range(1, N_ROUNDS + 1):
            args = argparse.Namespace(**vars(base), round=rnd)
            assert cmd_build(args) == 0
            for oid, e in json.loads((run / "manifest.json").read_text()).items():
                if e["round"] == rnd:
                    ranking = rng.sample(m.options, len(m.options))
                    body = json.dumps({"ranking": ranking, "private_note": "note", "statement": f"I back {ranking[0]}."})
                    (dispatch / f"{oid}.reply.json").write_text(f"```json\n{body}\n```" if rng.random() < 0.2 else body)
            assert cmd_collect(args) == 0
        assert cmd_tally(base) == 0
        last = (run / "r3" / "known" / "d08.prompt.md").read_text()
        assert "Round 2 statements" in last and "Your own record" in last and "[[" not in last
        hidden = (run / "r1" / "withheld" / "d08.prompt.md").read_text()
        assert "home health aide" not in hidden and "home health aide" in (run / "r1" / "known" / "d08.prompt.md").read_text()
        positions = Counter((i, p["name"]) for d in m.delegates for i, p in enumerate(m.plan_order(d)))
        assert set(positions.values()) == {3}, "plan order is not balanced"
    print("\nselftest ok")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("build", cmd_build), ("collect", cmd_collect)):
        p = sub.add_parser(name)
        p.add_argument("--run", required=True)
        p.add_argument("--round", type=int, required=True, choices=range(1, N_ROUNDS + 1))
        p.add_argument("--dispatch", required=True)
        if name == "build":
            p.add_argument("--conditions", nargs="+", default=list(CONDITIONS), choices=CONDITIONS)
        p.set_defaults(fn=fn)
    p = sub.add_parser("tally")
    p.add_argument("--run", required=True)
    p.set_defaults(fn=cmd_tally)
    sub.add_parser("selftest").set_defaults(fn=cmd_selftest)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
