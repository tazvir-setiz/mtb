import hashlib
from uuid import uuid4

from app.database.database import get_session
from app.database.models import ReviewDraft, ReviewRequest
from app.services.review_kind import preserve_review_kind


def get(review_id):
    with get_session() as session:
        return session.get(ReviewDraft, review_id)


def version(row, draft=None):
    draft = draft or get(row.id)
    if not draft:
        return row.fingerprint[:12]
    return hashlib.sha256((row.fingerprint + draft.revision).encode()).hexdigest()[:12]


def save(review_id, expected_version, text, reason, *, from_ai=False):
    with get_session() as session:
        row = session.get(ReviewRequest, review_id)
        draft = session.get(ReviewDraft, review_id)
        if (
            not row
            or row.status != ("sending" if from_ai else "pending")
            or version(row, draft) != expected_version
        ):
            return False
        if not draft:
            draft = ReviewDraft(review_id=review_id)
            session.add(draft)
        draft.text = text
        draft.revision = uuid4().hex
        row.status = "pending"
        row.reason = preserve_review_kind(row.reason, reason)
        row.preview = text[:2500]
        row.notified = "[]"
        return True
