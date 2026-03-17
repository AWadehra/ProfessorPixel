import json

from google.adk.agents import LlmAgent
from contract_negotiator.models.schemas import FinalReport


def _mediator_instruction(ctx):
    clauses = ctx.state.get("clauses", {})
    buyer_analysis = ctx.state.get("buyer_analysis", {})
    seller_analysis = ctx.state.get("seller_analysis", {})
    debate_history = ctx.state.get("debate_history", [])
    return f"""You are a neutral senior mediator. Produce a structured risk assessment.

SCORING GUIDE for overall_fairness_score:
  1-3: Severely buyer-hostile (missing liability caps, broad IP assignment, no termination rights)
  4:   Moderately buyer-hostile
  5:   Balanced
  6:   Moderately seller-hostile
  7-10: Severely seller-hostile (unlimited liability, onerous warranty, restrictive payment)

PRIORITY DEFINITIONS for each risk_item:
  critical: clause could result in financial loss >$10k, litigation, or data breach
  important: clause is unfair but the harm is bounded and negotiable
  minor: clause is suboptimal but standard in the industry

RECOMMENDATION LOGIC:
  - "sign as-is" only if fairness_score is 4-6 AND no critical items exist
  - "negotiate" if any important items exist — list exact clause numbers
  - "walk away" if two or more critical items exist with no plausible counterproposal

You have the full debate history. If a side conceded a point in round 2 or 3, weight that concession
in your recommendation — it signals the party knows their position is weak.

Contract clauses: {json.dumps(clauses, indent=2, default=str)}
Buyer's analysis: {json.dumps(buyer_analysis, indent=2, default=str)}
Seller's analysis: {json.dumps(seller_analysis, indent=2, default=str)}
Debate history: {json.dumps(debate_history, indent=2, default=str)}"""


mediator = LlmAgent(
    name="Mediator",
    model="gemini-2.5-flash",
    output_schema=FinalReport,
    output_key="final_report",
    description="Neutral mediator that synthesizes both perspectives",
    instruction=_mediator_instruction,
)
