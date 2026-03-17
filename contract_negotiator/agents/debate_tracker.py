import json

from google.adk.agents import LlmAgent, BaseAgent, LoopAgent
from google.adk.events import Event, EventActions
from contract_negotiator.models.schemas import Rebuttal

MAX_DEBATE_ROUNDS = 3


def _buyer_rebuttal_instruction(ctx):
    seller_analysis = ctx.state.get("seller_analysis", {})
    buyer_analysis = ctx.state.get("buyer_analysis", {})
    debate_history = ctx.state.get("debate_history", [])
    debate_round = ctx.state.get("debate_round", 1)
    return f"""You are the buyer's attorney in round {debate_round} of contract negotiations.
Set "perspective" to "buyer" and "round_number" to the current round number.

THE GOAL OF THIS ROUND:
- Your "points" list must directly address specific arguments from the seller's analysis.
  Each point MUST name the clause number it concerns (e.g., "Regarding Clause 4 (Liability Cap)...").
- Do NOT simply restate your original analysis. This is a rebuttal — engage with what they said.
- Concede a point only if the seller made a genuinely valid argument. One or two concessions per
  round signals credibility; zero concessions every round signals you're not listening.
- Add to "new_concerns" only issues you discovered by READING the seller's analysis that you
  missed in your original pass. Do not recycle existing concerns.

REBUTTAL QUALITY EXAMPLES:
  BAD: "We maintain Clause 4 is problematic for our client."
  GOOD: "Seller argues Clause 4's one-month cap is 'industry standard.' That is false —
    SaaS contracts for enterprise clients routinely carry 12-month or $500k caps (see Salesforce
    MSA Section 14.2). We will not accept less than total fees paid in the contract year."

  BAD: "We concede nothing."
  GOOD: "We concede Clause 9's force majeure language is reasonable and withdraw our objection."

Seller's analysis: {json.dumps(seller_analysis, indent=2, default=str)}
Your previous analysis: {json.dumps(buyer_analysis, indent=2, default=str)}
Previous debate history: {json.dumps(debate_history, indent=2, default=str)}
Current round: {debate_round}"""


buyer_rebuttal = LlmAgent(
    name="BuyerRebuttal",
    model="gemini-2.5-flash",
    output_schema=Rebuttal,
    output_key="buyer_rebuttal",
    description="Buyer's rebuttal in debate",
    instruction=_buyer_rebuttal_instruction,
)


def _seller_rebuttal_instruction(ctx):
    buyer_analysis = ctx.state.get("buyer_analysis", {})
    buyer_rebuttal = ctx.state.get("buyer_rebuttal", {})
    seller_analysis = ctx.state.get("seller_analysis", {})
    debate_history = ctx.state.get("debate_history", [])
    debate_round = ctx.state.get("debate_round", 1)
    return f"""You are the seller's attorney in round {debate_round} of contract negotiations.
Set "perspective" to "seller" and "round_number" to the current round number.

THE GOAL OF THIS ROUND:
- Your "points" list must directly address specific arguments the buyer raised.
  Each point MUST name the clause number it concerns (e.g., "Regarding Clause 7 (Warranty)...").
- Do NOT simply restate your original analysis. Engage specifically with what they said.
- Concede a point where the buyer raised a legitimate concern. Selective concessions strengthen
  your credibility on the issues you hold firm.
- Add to "new_concerns" only issues you discovered by reading the buyer's arguments that you
  missed originally.

REBUTTAL QUALITY EXAMPLES:
  BAD: "Our liability cap in Clause 4 is standard and we stand by it."
  GOOD: "Buyer claims one-month cap is below industry standard. We counter: this contract is for
    a $10k/year tool, not enterprise infrastructure. A $10k cap (one year's fees) is proportionate
    and consistent with our standard terms. We will consider raising to 3 months but no further."

  BAD: "We concede nothing — every clause is fair."
  GOOD: "We concede Clause 12's 90-day warranty is shorter than buyer's standard. We will extend
    to 180 days."

Buyer's analysis: {json.dumps(buyer_analysis, indent=2, default=str)}
Buyer's rebuttal: {json.dumps(buyer_rebuttal, indent=2, default=str)}
Your previous analysis: {json.dumps(seller_analysis, indent=2, default=str)}
Previous debate history: {json.dumps(debate_history, indent=2, default=str)}
Current round: {debate_round}"""


seller_rebuttal = LlmAgent(
    name="SellerRebuttal",
    model="gemini-2.5-flash",
    output_schema=Rebuttal,
    output_key="seller_rebuttal",
    description="Seller's rebuttal in debate",
    instruction=_seller_rebuttal_instruction,
)


class DebateTracker(BaseAgent):
    """Tracks debate rounds, accumulates history, and validates rebuttal content."""

    name: str = "DebateTracker"
    description: str = "Tracks debate rounds and accumulates debate history"

    async def _run_async_impl(self, ctx):
        current_round = ctx.session.state.get("debate_round", 1)

        buyer_content = ctx.session.state.get("buyer_rebuttal", "")
        seller_content = ctx.session.state.get("seller_rebuttal", "")

        # Detect failed/empty rounds
        buyer_empty = not buyer_content or len(str(buyer_content).strip()) < 20
        seller_empty = not seller_content or len(str(seller_content).strip()) < 20

        history = ctx.session.state.get("debate_history", [])
        history.append(
            {
                "round": current_round,
                "buyer_rebuttal": buyer_content,
                "seller_rebuttal": seller_content,
                "buyer_failed": buyer_empty,
                "seller_failed": seller_empty,
            }
        )
        ctx.session.state["debate_history"] = history

        # Increment round for the next iteration
        ctx.session.state["debate_round"] = current_round + 1

        # Early exit if 2 consecutive rounds have failures
        recent_failures = sum(
            1 for r in history[-2:]
            if r.get("buyer_failed") or r.get("seller_failed")
        )
        failure_escalate = recent_failures >= 2

        should_stop = (current_round >= MAX_DEBATE_ROUNDS) or failure_escalate

        if failure_escalate:
            ctx.session.state["debate_terminated_early"] = True

        yield Event(
            author=self.name,
            actions=EventActions(escalate=should_stop),
        )


debate_tracker = DebateTracker()

debate_loop = LoopAgent(
    name="DebateRounds",
    description="Multi-round adversarial debate between buyer and seller lawyers",
    max_iterations=MAX_DEBATE_ROUNDS,
    sub_agents=[buyer_rebuttal, seller_rebuttal, debate_tracker],
)
