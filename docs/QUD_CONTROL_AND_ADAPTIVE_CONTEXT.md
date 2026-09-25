# Immediate QUD, Hierarchical Action Policy, and Adaptive State Context

## Why

A raw list of OPEN questions is not enough for a controlled debate. Multiple surface questions in one turn can express one immediate issue, and an older unrelated OPEN question should not automatically reappear after a newer issue has been resolved.

This layer treats question handling as a control problem:

```text
Debate State
  -> Question grouping / Immediate QUD
  -> TurnTask
  -> task-compatible Action x Target
  -> available State-reference working set
  -> Draft / validation / repair
  -> adaptive State Patch working set
```

## Immediate QUD

Questions from the same speaker and source turn that target the same semantic facet are treated as one QUD group even when the Patch extractor emitted multiple `ASK_QUESTION` operations.

The latest member is the current formulation. A substantive resolution of one member resolves the QUD group for planning purposes.

Only the newest opponent QUD is automatically answerable. Once that newest QUD is resolved, older unrelated OPEN questions are not automatically resurrected.

The Patch prompt additionally instructs the extractor to represent thematically continuous multi-question turns as one `ASK_QUESTION` when one answer would substantially resolve the whole unit.

## Task before Action

`TurnTask` constrains the set of legal strategic Actions.

For `ANSWER_OPEN_QUESTION`:

- if the question targets the responder's own facet: `DEFEND_CLAIM` / `REVISE_CLAIM`
- if it targets the opponent's facet: `REFUTE_CLAIM` / `CONCEDE_LOCAL`

The target is the current proposition in the same semantic facet. Persona preference only chooses among these compatible moves.

`ANSWER_OPEN_QUESTION` and `ADDRESS_AUDIENCE` are response obligations. If the TurnTask advances and stance remains compliant, failure to fully realize a secondary Action by itself does not force a draft retry.

Response obligations may reuse an Action-target pair that was used earlier, because answering a new QUD is a new conversational obligation.

## Repair feedback

Typed retry feedback contains:

- failure code
- failure location
- observed validator reason
- preserved successful behavior
- admissible repairs
- forbidden changes
- current Action / Target / TurnTask

The second attempt is a targeted repair. Planner-level failures can trigger Action/Target replanning before the third attempt.

## State-reference working set

The surface model can use `[[C..]]` / `[[Q..]]` only from the current working set:

- selected Action targets
- TurnTask / Immediate-QUD references
- the QUD's proposition target
- representative/current forms of targeted facets
- references already visible in the last three committed turns

This avoids a contradiction where recent transcript text exposes a valid State marker but the local validator rejects it.

## Adaptive Patch context

Patch extraction no longer scales with the entire State graph.

Relevance seeds:

1. current Action targets
2. explicit State references in the committed utterance
3. Immediate-QUD target
4. semantic facet representative/current nodes
5. one-hop argumentative neighbors
6. at most two recent propositions per speaker

The proposition working set is capped at 10 nodes. Recent question history keeps at most the last two question nodes in addition to explicitly selected/current QUD questions.

Debug mode records `context_counts` so later live runs can compare State-Patch prompt growth.
