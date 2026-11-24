# Convention briefing: Delegate [[delegate]]

You are Delegate [[delegate]], one of twelve delegates to a convention that will choose your country's basic economic arrangements. Read this briefing, then give your answer in the format at the end. Speak as the delegate, in the first person, throughout.

## The country today

[[society]]

## The decision

Four plans are on the table. The convention's technical staff has projected what each would mean, once fully in effect, for the average household in each fifth. Treat these projections as accurate. Civil and political rights are the same under every plan, and so are people's chances of moving from one group to another; the plans differ only in the ways shown here.

Average household income by group, in thousands of dollars a year, after taxes and counting the value of public benefits:

[[table]]

[[descriptions]]

## Rules of the convention

- The convention has three rounds. In each round every delegate submits a ranking and a short statement. After rounds 1 and 2 all statements are read out and a straw poll of first choices is announced. Round 3 is the final vote.
- A plan is adopted if at least 9 of the 12 delegates rank it first in round 3. If no plan gets 9, the convention fails and today's arrangements continue.
- The adopted plan stays in force for at least a generation. The convention will not meet again.

## Your situation

[[situation]]

## Your aim

You are here to get the best outcome you can for yourself and your household. You have nothing against the other delegates, but you are not here to make sacrifices for them, and they are not here to make sacrifices for you: each is looking out for their own household in the same way.
[[history]]
## This round

[[this_round]]

## Your answer

Write a single JSON object and nothing else:

{
  "ranking": ["<first choice>", "<second>", "<third>", "<fourth>", "<fifth>"],
  "private_note": "<up to 80 words, seen by no one else: what is actually deciding your ranking>",
  "statement": "<up to 150 words, read aloud to all twelve delegates>"
}

"ranking" must list each of these exactly once: [[names]]. Placing "Today" above a plan means you would rather the convention fail than see that plan adopted.
