"""One-case semantic regression probe for the preserved Turn 4 mismatch."""

import argparse
import json
from pathlib import Path

from src.debate_engine.combined_compliance import judge_combined
from src.debate_engine.debate_harness import load_config, select_debaters
from src.debate_engine.stance_compliance import StanceAssignment


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=Path("etc/fixtures/action_fidelity_audit.json"))
    parser.add_argument("--turn", type=int, default=4)
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError(f"Output exists: {args.output}")
    case = next(item for item in json.loads(args.fixture.read_text(encoding="utf-8"))["cases"] if item["turn_id"] == args.turn)
    provider = select_debaters(load_config(args.env), args.model)["DEBATER_A"]
    # The preserved source run assigns B to 찍먹 at Turn 4.
    assignment = StanceAssignment("탕수육은 소스에 찍어 먹는 편이 낫다", "탕수육은 소스를 부어 먹는 편이 낫다")
    verdict, meta = judge_combined(provider, action=case["selected_action"], target_id=case["target_id"], target_text=case["target_text"], utterance=case["utterance"], assignment=assignment, phase=case["phase"].lower(), timeout=args.timeout)
    result = {"turn_id": args.turn, "action_fidelity": verdict.action_fidelity.value, "stance_compliance": verdict.stance_compliance.value, "action_reason": verdict.action_reason, "stance_reason": verdict.stance_reason, "usage": meta["usage"], "known_mismatch_not_accepted_as_aligned": verdict.action_fidelity.value != "ALIGNED"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["known_mismatch_not_accepted_as_aligned"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
