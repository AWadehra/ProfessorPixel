from pydantic import BaseModel, Field


class Clause(BaseModel):
    number: int = Field(description="Clause number")
    title: str = Field(description="Short title of the clause")
    text: str = Field(description="Full text of the clause")
    category: str = Field(
        description="Category: payment, liability, termination, IP, confidentiality, indemnification, warranty, dispute, other"
    )


class ContractClauses(BaseModel):
    contract_type: str = Field(
        description="Type of contract: SaaS, employment, freelance, NDA, lease, other"
    )
    parties: list[str] = Field(
        description="Names or roles of the parties involved"
    )
    clauses: list[Clause] = Field(description="Extracted clauses")


class ClauseRisk(BaseModel):
    clause_number: int
    risk_level: str = Field(description="high, medium, low")
    concern: str = Field(description="What's problematic about this clause")
    proposed_change: str = Field(
        description="Specific suggested rewording or addition"
    )
    legal_reasoning: str = Field(description="Why this matters legally")


class LawyerAnalysis(BaseModel):
    perspective: str = Field(description="buyer or seller")
    overall_risk: str = Field(description="high, medium, low")
    summary: str = Field(description="2-3 sentence overall assessment")
    clause_risks: list[ClauseRisk]
    missing_clauses: list[str] = Field(
        description="Important clauses that are absent from the contract"
    )


class RebuttalPoint(BaseModel):
    original_concern: str = Field(
        description="What the other side raised"
    )
    counter_argument: str = Field(
        description="Why that concern is invalid or overstated"
    )
    concession: str | None = Field(
        default=None,
        description="Any point where this side agrees with the other",
    )


class Rebuttal(BaseModel):
    round_number: int
    perspective: str
    points: list[RebuttalPoint]
    new_concerns: list[ClauseRisk] = Field(
        default_factory=list,
        description="New issues discovered while reviewing the other side's analysis",
    )


class RiskItem(BaseModel):
    clause_number: int
    clause_title: str
    buyer_risk: str
    seller_risk: str
    buyer_concern: str
    seller_concern: str
    mediator_recommendation: str
    priority: str = Field(description="critical, important, minor")


class FinalReport(BaseModel):
    contract_type: str
    parties: list[str]
    overall_fairness_score: int = Field(
        description="1-10, where 5 is balanced, <5 favors seller, >5 favors buyer"
    )
    executive_summary: str
    risk_items: list[RiskItem]
    missing_protections_buyer: list[str]
    missing_protections_seller: list[str]
    recommendation: str = Field(
        description="Final recommendation: sign as-is, negotiate specific clauses, or walk away"
    )


class RedlineClause(BaseModel):
    clause_number: int
    original_text: str = Field(description="The original clause text exactly as written")
    revised_text: str = Field(description="The suggested revised text with changes applied")
    change_summary: str = Field(description="One-sentence summary of what changed and why")
    changed: bool = Field(description="True if the clause was modified, False if kept as-is")


class RedlinedContract(BaseModel):
    contract_type: str
    overall_summary: str = Field(description="2-3 sentence summary of all changes made")
    total_changes: int = Field(description="Number of clauses that were modified")
    clauses: list[RedlineClause]
    new_clauses: list[str] = Field(
        default_factory=list,
        description="New clauses that should be added to the contract"
    )
