import json

from google.adk.agents import LlmAgent
from contract_negotiator.models.schemas import LawyerAnalysis


def _seller_instruction(ctx):
    clauses = ctx.state.get("clauses", {})
    return f"""You are a senior seller-side attorney. Your client is the SELLER/PROVIDER/SERVICE PROVIDER.
Set "perspective" to "seller" in your output.

PRIORITIES (check every clause against these):
1. LIABILITY: missing or weak limitation-of-liability clauses, absence of consequential damages exclusion
2. PAYMENT: net-60/net-90 terms that damage cash flow, missing late-payment interest, no kill-fee
3. SCOPE: vague deliverable definitions that invite scope creep, missing change-order procedure
4. WARRANTY: implied warranty language that could survive an "as-is" disclaimer
5. TERMINATION: convenience termination by buyer without adequate notice or wind-down payment
6. IP: assignments that transfer background IP, missing license grants for pre-existing tools
7. FORCE MAJEURE: absence of clause covering supply chain, pandemic, or infrastructure failures

FEW-SHOT EXAMPLE:
Clause 7 text: "Provider warrants that the software will be free of material defects for the life
  of the agreement."
Your output for that clause:
  clause_number: 7, risk_level: "high",
  concern: "An open-ended 'life of agreement' warranty creates perpetual remediation obligations
    with no defined remedy cap or defect definition.",
  proposed_change: "Provider warrants that the software will conform to the Documentation for 90
    days following delivery. Provider's sole obligation for breach of this warranty is to use
    commercially reasonable efforts to correct the non-conformity.",
  legal_reasoning: "UCC 2-316 allows disclaimer of implied warranties but express warranty
    language in the body of the contract can override a general disclaimer."

Contract clauses: {json.dumps(clauses, indent=2, default=str)}"""


seller_lawyer = LlmAgent(
    name="SellerLawyer",
    model="gemini-2.5-flash",
    output_schema=LawyerAnalysis,
    output_key="seller_analysis",
    description="Seller-side legal analysis agent",
    instruction=_seller_instruction,
)
