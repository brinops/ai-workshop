"""Structured contract for Claude's workshop stages."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

from app.integrations.training_jira import AppendResult, JiraIssue

EvidencePath = Literal["demo/booking/service.py", "demo/booking/test_booking.py"]
EVIDENCE_PATHS = ("demo/booking/service.py", "demo/booking/test_booking.py")
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SlackText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=3000)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(Contract):
    path: EvidencePath
    symbol: Text


class DescriptionBlock(Contract):
    heading: Text
    steps: list[Text] = Field(min_length=1)
    actual: Text
    expected: Text
    evidence: list[Evidence]
    open_questions: list[Text]


class Reply(Contract):
    actor: Literal["agent", "reporter"]
    text: Text


class BlockerNotice(Contract):
    reason: Text
    next_step: Text


class StageInput(Contract):
    stage: Literal["triage", "reply", "request_revision", "revision", "result", "blocker", "recovery"]
    issue: JiraIssue
    replies: list[Reply] = Field(default_factory=list)
    follow_up_rounds_used: Literal[0, 1] = 0
    previous_block: DescriptionBlock | None = None
    write_result: AppendResult | None = None
    blocker: BlockerNotice | None = None


class StageOutput(Contract):
    schema_version: Literal[1]
    slack_text: SlackText


class Questions(StageOutput):
    kind: Literal["ask_questions"]
    questions: list[Text] = Field(min_length=1, max_length=3)


class FollowUp(Questions):
    questions: list[Text] = Field(min_length=1, max_length=1)


class Proposal(StageOutput):
    kind: Literal["propose_description_append"]
    block: DescriptionBlock


class NeedsIntervention(StageOutput):
    kind: Literal["needs_intervention"]
    reason: Text


class ReportResult(StageOutput):
    kind: Literal["report_result"]


class ReportBlocker(StageOutput):
    kind: Literal["report_blocker"]


class RequestFeedback(StageOutput):
    kind: Literal["request_revision"]


def output_contract(request: StageInput) -> TypeAdapter:
    if request.stage == "triage":
        return TypeAdapter(Questions | Proposal)
    if request.stage == "result":
        return TypeAdapter(ReportResult)
    if request.stage == "blocker":
        return TypeAdapter(ReportBlocker)
    if request.stage == "request_revision":
        return TypeAdapter(RequestFeedback)
    if request.stage in ("revision", "recovery") or request.follow_up_rounds_used:
        return TypeAdapter(Proposal | NeedsIntervention)
    return TypeAdapter(FollowUp | Proposal | NeedsIntervention)


def claude_output_schema(contract: TypeAdapter) -> dict:
    schema = contract.json_schema()
    variants = schema.get("anyOf")
    if not variants:
        return schema

    # Claude tools require a root object. The backend still enforces the exact union.
    definitions = schema["$defs"]
    properties = {}
    kinds = []
    for variant in variants:
        fields = definitions[variant["$ref"].rsplit("/", 1)[-1]]["properties"]
        properties.update(fields)
        kinds.append(fields["kind"]["const"])
    properties["kind"] = {"type": "string", "enum": kinds}
    return {
        "type": "object",
        "properties": properties,
        "required": ["schema_version", "kind", "slack_text"],
        "additionalProperties": False,
        "$defs": definitions,
    }
