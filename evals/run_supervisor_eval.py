"""Evaluate the supervisor's guardrail and routing decisions against a labelled set.

Calls the real Gemini model (2 calls per request), so it needs GOOGLE_API_KEY.
No database or MCP servers are needed: only supervisor_agent() is exercised.

Usage:
    uv run python evals/run_supervisor_eval.py [--delay 4]
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import supervisor_agent  # noqa: E402

DATASET = Path(__file__).with_name("supervisor_dataset.json")
RESULTS_DIR = Path(__file__).with_name("results")

SPECIALISTS = ["flight_agent", "hotel_agent", "weather_agent", "budget_agent"]

# Cost per specialist, read from backend.py. Hotel uses no LLM call; weather
# makes one hidden call through extract_destination().
LLM_CALLS = {"flight_agent": 1, "hotel_agent": 0, "weather_agent": 1, "budget_agent": 1}
MCP_CALLS = {"flight_agent": 2, "hotel_agent": 1, "weather_agent": 2, "budget_agent": 0}
ITINERARY_AND_FINAL = 2


def routed_cost(allowed, agents):
    """(LLM calls, MCP calls) for one request with supervisor routing."""
    if not allowed:
        return 1, 0  # guardrail only
    llm = 2 + sum(LLM_CALLS[a] for a in agents) + ITINERARY_AND_FINAL
    mcp = sum(MCP_CALLS[a] for a in agents)
    return llm, mcp


def run_all_cost(allowed):
    """Baseline: guardrail kept, but no routing call and every specialist runs."""
    if not allowed:
        return 1, 0
    return 1 + sum(LLM_CALLS.values()) + ITINERARY_AND_FINAL, sum(MCP_CALLS.values())


def pct(n, d):
    return f"{100 * n / d:.1f}%" if d else "n/a"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=4.0, help="seconds between requests (rate limits)")
    args = parser.parse_args()

    cases = json.loads(DATASET.read_text(encoding="utf-8"))
    rows = []

    for i, case in enumerate(cases, 1):
        out = supervisor_agent({"user_query": case["query"], "llm_calls": 0})
        allowed = out["guardrail_allowed"]
        predicted = [a for a in out["selected_agents"] if a in SPECIALISTS]
        fallback = "fallback" in out.get("guardrail_reason", "") or "fallback" in out.get(
            "supervisor_reasoning", ""
        )
        rows.append(
            {
                **case,
                "pred_allowed": allowed,
                "pred_agents": predicted,
                "fallback": fallback,
                "reason": out.get("guardrail_reason") or out.get("supervisor_reasoning", ""),
            }
        )
        mark = "ok " if allowed == case["allowed"] else "BAD"
        print(f"[{i:>2}/{len(cases)}] {mark} allowed={allowed!s:<5} agents={predicted}  {case['query'][:60]}")
        if i < len(cases):
            time.sleep(args.delay)

    # ---- Guardrail ----
    tp = sum(r["allowed"] is False and r["pred_allowed"] is False for r in rows)  # correctly blocked
    fp = sum(r["allowed"] is True and r["pred_allowed"] is False for r in rows)   # travel wrongly blocked
    fn = sum(r["allowed"] is False and r["pred_allowed"] is True for r in rows)   # bad request let through
    correct = sum(r["allowed"] == r["pred_allowed"] for r in rows)
    n_travel = sum(r["allowed"] for r in rows)
    n_block = len(rows) - n_travel

    # ---- Routing (travel requests the guardrail allowed) ----
    routed = [r for r in rows if r["allowed"] and r["pred_allowed"]]
    exact = sum(set(r["agents"]) == set(r["pred_agents"]) for r in routed)
    per_agent = {}
    for agent in SPECIALISTS:
        a_tp = sum(agent in r["agents"] and agent in r["pred_agents"] for r in routed)
        a_fp = sum(agent not in r["agents"] and agent in r["pred_agents"] for r in routed)
        a_fn = sum(agent in r["agents"] and agent not in r["pred_agents"] for r in routed)
        per_agent[agent] = (a_tp, a_fp, a_fn)

    # ---- Cost: routing vs running every agent ----
    route_llm = route_mcp = all_llm = all_mcp = 0
    for r in rows:
        l, m = routed_cost(r["pred_allowed"], r["pred_agents"])
        route_llm, route_mcp = route_llm + l, route_mcp + m
        l, m = run_all_cost(r["pred_allowed"])
        all_llm, all_mcp = all_llm + l, all_mcp + m

    lines = [
        f"Supervisor evaluation - {datetime.now():%Y-%m-%d %H:%M}",
        f"Dataset: {len(rows)} requests ({n_travel} travel, {n_block} should be blocked)",
        "",
        "GUARDRAIL",
        f"  Accuracy:                {correct}/{len(rows)} = {pct(correct, len(rows))}",
        f"  Block precision:         {pct(tp, tp + fp)}  (of blocked requests, how many deserved it)",
        f"  Block recall:            {pct(tp, tp + fn)}  (of bad requests, how many were caught)",
        f"  False-block rate:        {fp}/{n_travel} travel requests wrongly blocked",
        f"  Missed blocks:           {fn}/{n_block} bad requests let through",
        f"  Fallbacks (bad JSON/err): {sum(r['fallback'] for r in rows)}",
        "",
        "ROUTING (allowed travel requests)",
        f"  Exact agent-set match:   {exact}/{len(routed)} = {pct(exact, len(routed))}",
    ]
    for agent, (a_tp, a_fp, a_fn) in per_agent.items():
        lines.append(
            f"  {agent:<14} precision {pct(a_tp, a_tp + a_fp):>6}   recall {pct(a_tp, a_tp + a_fn):>6}"
        )
    lines += [
        "",
        "COST: supervisor routing vs running every agent (estimated from decisions)",
        f"  LLM calls:  {route_llm} vs {all_llm}  -> saved {pct(all_llm - route_llm, all_llm)}",
        f"  MCP calls:  {route_mcp} vs {all_mcp}  -> saved {pct(all_mcp - route_mcp, all_mcp)}",
    ]

    mistakes = [
        r for r in rows
        if r["allowed"] != r["pred_allowed"]
        or (r["allowed"] and r["pred_allowed"] and set(r["agents"]) != set(r["pred_agents"]))
    ]
    if mistakes:
        lines += ["", "MISTAKES"]
        for r in mistakes:
            lines.append(
                f"  #{r['id']} {r['query'][:70]}\n"
                f"      expected allowed={r['allowed']} agents={r['agents']}\n"
                f"      got      allowed={r['pred_allowed']} agents={r['pred_agents']}  ({r['reason'][:80]})"
            )

    report = "\n".join(lines)
    print("\n" + report)

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (RESULTS_DIR / f"supervisor_eval_{stamp}.txt").write_text(report, encoding="utf-8")
    (RESULTS_DIR / f"supervisor_eval_{stamp}.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
