import json

from google.adk.agents import LlmAgent
from contract_negotiator.models.schemas import RedlinedContract

# Idea 6: Static instruction prefix FIRST — maximizes Vertex AI implicit prefix caching
_REDLINER_STATIC = """You are a legal document editor. Given the original contract clauses and the mediator's
final report, produce a redlined version of the contract.

RULES:
1. For each clause, provide the EXACT original text and your revised text.
2. Only modify clauses that the mediator flagged as "critical" or "important".
3. For "minor" items, keep the original text unchanged (set changed=false).
4. Revisions must be specific legal language, not vague suggestions.
5. Include new_clauses for any protections the mediator said were missing.
6. Keep revised text proportional — don't triple the length of a clause.

REVISION STYLE:
- Be precise: "Provider's liability shall not exceed total fees paid in the preceding 12 months"
  NOT: "Provider's liability should be higher"
- Preserve the contract's voice and formatting style
- Mark every change with changed=true
"""


def _redliner_instruction(ctx):
    clauses = ctx.state.get("clauses", {})
    final_report = ctx.state.get("final_report", {})
    buyer_analysis = ctx.state.get("buyer_analysis", {})
    seller_analysis = ctx.state.get("seller_analysis", {})
    return f"""{_REDLINER_STATIC}
Original clauses: {json.dumps(clauses, indent=2, default=str)}
Mediator's report: {json.dumps(final_report, indent=2, default=str)}
Buyer's analysis: {json.dumps(buyer_analysis, indent=2, default=str)}
Seller's analysis: {json.dumps(seller_analysis, indent=2, default=str)}"""


redliner = LlmAgent(
    name="Redliner",
    model="gemini-2.5-flash",
    output_schema=RedlinedContract,
    output_key="redlined_contract",
    description="Generates a redlined version of the contract with tracked changes",
    instruction=_redliner_instruction,
)
