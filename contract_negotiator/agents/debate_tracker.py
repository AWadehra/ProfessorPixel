import json

from google.adk.agents import LlmAgent, BaseAgent, LoopAgent, ParallelAgent
from google.adk.events import Event, EventActions
from contract_negotiator.models.schemas import Rebuttal

MAX_DEBATE_ROUNDS = 3


# ── Debate history summarizer (Idea 4) ──
# Compact summary instead of full JSON dump — saves ~600-800 tokens per round
def summarize_debate_history(history):
    """Produce a compact summary of prior debate rounds for injection into prompts."""
    if not history:
        return "No prior debate rounds."
    lines = []
    for r in history:
        rnd = r.get("round", "?")
        parts = []
        for side in ("buyer_rebuttal", "seller_rebuttal"):
            label = "Buyer" if "buyer" in side else "Seller"
            content = r.get(side, {})
            if r.get(side.replace("rebuttal", "failed"), False):
                parts.append(f"  {label}: [no substantive rebuttal]")
                continue
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except Exception:
                    parts.append(f"  {label}: {str(content)[:200]}")
                    continue
            if isinstance(content, dict):
                points = content.get("points", [])
                concessions = [p for p in points if p.get("concession")]
                new_concerns = content.get("new_concerns", [])
                summary_parts = []
                if concessions:
                    conc_list = "; ".join(
                        p.get("concession", "")[:80] for p in concessions
                    )
                    summary_parts.append(f"conceded: {conc_list}")
                contested = [p for p in points if not p.get("concession")]
                if contested:
                    contested_list = "; ".join(
                        p.get("counter_argument", "")[:60] for p in contested[:3]
                    )
                    summary_parts.append(
                        f"contested {len(contested)} points: {contested_list}"
                    )
                if new_concerns:
                    nc_list = "; ".join(
                        f"Clause {nc.get('clause_number', '?')}: {nc.get('concern', '')[:40]}"
                        for nc in new_concerns
                    )
                    summary_parts.append(f"new concerns: {nc_list}")
                parts.append(f"  {label}: {'; '.join(summary_parts) or 'restated position'}")
            else:
                parts.append(f"  {label}: {str(content)[:200]}")
        lines.append(f"Round {rnd}:\n" + "\n".join(parts))
    return "\n".join(lines)


# ── Rebuttal instructions ──
# Static legal instruction comes FIRST (Idea 6: maximizes Vertex AI implicit prefix caching)
# Dynamic context injected AFTER the stable prefix

_BUYER_REBUTTAL_STATIC = """You are the buyer's attorney in a contract negotiation debate.
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
"""

_SELLER_REBUTTAL_STATIC = """You are the seller's attorney in a contract negotiation debate.
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
"""


def _buyer_rebuttal_instruction(ctx):
    seller_analysis = ctx.state.get("seller_analysis", {})
    buyer_analysis = ctx.state.get("buyer_analysis", {})
    debate_history = ctx.state.get("debate_history", [])
    debate_round = ctx.state.get("debate_round", 1)
    return f"""{_BUYER_REBUTTAL_STATIC}
Current round: {debate_round}
Seller's analysis: {json.dumps(seller_analysis, indent=2, default=str)}
Your previous analysis: {json.dumps(buyer_analysis, indent=2, default=str)}
Previous debate: {summarize_debate_history(debate_history)}"""


buyer_rebuttal = LlmAgent(
    name="BuyerRebuttal",
    model="gemini-2.5-flash",
    output_schema=Rebuttal,
    output_key="buyer_rebuttal",
    description="Buyer's rebuttal in debate",
    instruction=_buyer_rebuttal_instruction,
)


def _seller_rebuttal_instruction(ctx):
    # Idea 1: Seller no longer reads current-round buyer_rebuttal — enabling parallel execution.
    # Seller responds to buyer's original analysis + debate history (which has prior rounds).
    buyer_analysis = ctx.state.get("buyer_analysis", {})
    seller_analysis = ctx.state.get("seller_analysis", {})
    debate_history = ctx.state.get("debate_history", [])
    debate_round = ctx.state.get("debate_round", 1)
    return f"""{_SELLER_REBUTTAL_STATIC}
Current round: {debate_round}
Buyer's analysis: {json.dumps(buyer_analysis, indent=2, default=str)}
Your previous analysis: {json.dumps(seller_analysis, indent=2, default=str)}
Previous debate: {summarize_debate_history(debate_history)}"""


seller_rebuttal = LlmAgent(
    name="SellerRebuttal",
    model="gemini-2.5-flash",
    output_schema=Rebuttal,
    output_key="seller_rebuttal",
    description="Seller's rebuttal in debate",
    instruction=_seller_rebuttal_instruction,
)


# ── Idea 1: Parallel rebuttals — buyer and seller argue simultaneously ──
parallel_rebuttals = ParallelAgent(
    name="ParallelRebuttals",
    description="Buyer and seller rebuttals run simultaneously",
    sub_agents=[buyer_rebuttal, seller_rebuttal],
)


class DebateTracker(BaseAgent):
    """Tracks debate rounds, accumulates history, detects convergence, and validates content."""

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

        # ── Idea 2: Convergence detection ──
        # After round 2+, check if both sides have converged (many concessions, no new issues)
        convergence_escalate = False
        if current_round >= 2 and not buyer_empty and not seller_empty:
            convergence_escalate = self._check_convergence(
                buyer_content, seller_content
            )
            if convergence_escalate:
                ctx.session.state["debate_converged"] = True

        should_stop = (
            (current_round >= MAX_DEBATE_ROUNDS)
            or failure_escalate
            or convergence_escalate
        )

        if failure_escalate:
            ctx.session.state["debate_terminated_early"] = True

        yield Event(
            author=self.name,
            actions=EventActions(escalate=should_stop),
        )

    @staticmethod
    def _check_convergence(buyer_content, seller_content):
        """Detect if debate positions have converged — no need for more rounds."""
        buyer_concessions = 0
        seller_concessions = 0
        buyer_new = 0
        seller_new = 0

        for side_content, label in [
            (buyer_content, "buyer"),
            (seller_content, "seller"),
        ]:
            data = side_content
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    return False  # Can't parse — don't assume convergence

            if not isinstance(data, dict):
                return False

            points = data.get("points", [])
            concessions = sum(1 for p in points if p.get("concession"))
            new_concerns = len(data.get("new_concerns", []))

            if label == "buyer":
                buyer_concessions = concessions
                buyer_new = new_concerns
            else:
                seller_concessions = concessions
                seller_new = new_concerns

        # Converged if: both sides made concessions and neither raised new concerns
        total_concessions = buyer_concessions + seller_concessions
        total_new = buyer_new + seller_new
        return total_concessions >= 2 and total_new == 0


debate_tracker = DebateTracker()

# Idea 1: LoopAgent now runs parallel rebuttals + tracker
debate_loop = LoopAgent(
    name="DebateRounds",
    description="Multi-round adversarial debate between buyer and seller lawyers",
    max_iterations=MAX_DEBATE_ROUNDS,
    sub_agents=[parallel_rebuttals, debate_tracker],
)
