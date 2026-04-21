#!/usr/bin/env python3
"""
SN13 operator submission quality checks.

Quality decides whether a submission can become miner truth. Storage records
the decision and resulting audit trail.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .desirability import DesirabilityMatch, DesirabilitySnapshot
from .intake import OperatorSubmission
from .models import DataEntity, DataSource, normalize_uri
from .policy import ScorableDecision, SN13Policy


class SubmissionStatus(str, Enum):
    ACCEPTED_SCORABLE = "accepted_scorable"
    ACCEPTED_NON_SCORABLE = "accepted_non_scorable"
    REJECTED = "rejected"


class RejectionReason(str, Enum):
    DUPLICATE_ENTITY = "duplicate_entity"
    MISSING_SOURCE_FIELD = "missing_source_field"
    SOURCE_PAYLOAD_MISMATCH = "source_payload_mismatch"
    EMPTY_CONTENT = "empty_content"


class QualityResult(BaseModel):
    """Quality decision for one operator submission."""

    model_config = {"frozen": True}

    submission_id: str
    operator_id: str
    status: SubmissionStatus
    reasons: list[str] = Field(default_factory=list)
    entity: Optional[DataEntity] = None
    desirability_match: Optional[DesirabilityMatch] = None
    scorable_decision: Optional[ScorableDecision] = None

    @property
    def accepted(self) -> bool:
        return self.status in {
            SubmissionStatus.ACCEPTED_SCORABLE,
            SubmissionStatus.ACCEPTED_NON_SCORABLE,
        }


class SubmissionQualityChecker:
    """Validates operator submissions before storage accepts them."""

    def __init__(
        self,
        *,
        policy: Optional[SN13Policy] = None,
        desirability_snapshot: Optional[DesirabilitySnapshot] = None,
    ):
        self.policy = policy or SN13Policy()
        self.desirability_snapshot = desirability_snapshot

    def assess(
        self,
        submission: OperatorSubmission,
        *,
        duplicate: bool = False,
        now: Optional[datetime] = None,
    ) -> QualityResult:
        reasons = self._validate_source_payload(submission)

        if duplicate:
            reasons.append(RejectionReason.DUPLICATE_ENTITY.value)

        entity = submission.to_data_entity()
        if reasons:
            return QualityResult(
                submission_id=submission.submission_id,
                operator_id=submission.operator_id,
                status=SubmissionStatus.REJECTED,
                reasons=reasons,
                entity=entity,
            )

        if self.desirability_snapshot:
            match, decision = self.desirability_snapshot.classify_entity(
                entity,
                policy=self.policy,
                now=now,
            )
        else:
            match = None
            decision = self.policy.classify_entity(entity, now=now)

        status = (
            SubmissionStatus.ACCEPTED_SCORABLE
            if decision.is_scorable
            else SubmissionStatus.ACCEPTED_NON_SCORABLE
        )
        return QualityResult(
            submission_id=submission.submission_id,
            operator_id=submission.operator_id,
            status=status,
            entity=entity,
            desirability_match=match,
            scorable_decision=decision,
        )

    def _validate_source_payload(self, submission: OperatorSubmission) -> list[str]:
        reasons: list[str] = []
        content = submission.content
        if not content:
            return [RejectionReason.EMPTY_CONTENT.value]

        if submission.source == DataSource.X:
            required = ("tweet_id", "username", "text", "url", "timestamp")
            text_fields = ("text",)
        elif submission.source == DataSource.REDDIT:
            required = ("id", "username", "url", "createdAt")
            text_fields = ("body", "title")
        else:
            required = ("url",)
            text_fields = ()

        missing = [field for field in required if not content.get(field)]
        if missing:
            reasons.append(f"{RejectionReason.MISSING_SOURCE_FIELD.value}:{'|'.join(missing)}")

        if text_fields and not any(str(content.get(field, "")).strip() for field in text_fields):
            reasons.append(RejectionReason.EMPTY_CONTENT.value)

        content_url = content.get("url")
        if content_url and normalize_uri(str(content_url)) != normalize_uri(submission.uri):
            reasons.append(RejectionReason.SOURCE_PAYLOAD_MISMATCH.value)

        return reasons
