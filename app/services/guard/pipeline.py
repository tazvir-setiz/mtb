import asyncio
import hashlib
import logging
import time
from dataclasses import replace

from app.services import ai_service
from app.services.ai_policy import AIProcessingError
from app.services.ai_transport import AIRequestError
from app.services.guard.budget import Budget, active_budget
from app.services.guard.contracts import Verification
from app.services.guard_models import Label, ModerationResult
from app.services.guard_runtime import runtime
from app.services.text_normalizer import normalize_text
from app.services.text_sanitizer import publication_is_clean, sanitize_text, username_replacement

logger = logging.getLogger(__name__)
PIPELINE_VERSION = "2"


class GuardPipeline:
    def __init__(self, config, limits, context, policy, disabled_labels=()):
        self.disabled_labels = disabled_labels
        self.config, self.limits, self.context, self.policy = config, limits, context, policy
        self.provider = hashlib.sha256(
            repr((config.base_url, config.model, config.api_key)).encode()
        ).hexdigest()
        self.version = hashlib.sha256((PIPELINE_VERSION + policy).encode()).hexdigest()[:12]
        self.replacement = username_replacement()
        self.budget = Budget(limits.total_timeout_seconds, limits.max_stages, limits.max_requests)

    async def call(self, stage, text, **kwargs):
        self.budget.stage()
        if runtime.unavailable(self.provider):
            runtime.metrics["circuit_skips"] += 1
            raise AIRequestError("circuit_open")
        limits = replace(
            self.limits, timeout_seconds=min(self.limits.timeout_seconds, self.budget.remaining())
        )
        runtime.metrics["ai_calls"] += 1
        runtime.metrics["ai_fallbacks"] += 1
        runtime.metrics[f"stage_{stage}"] += 1
        started = time.monotonic()
        logger.info(
            "Guard stage=%s policy=%s stage_count=%d remaining=%.2fs",
            stage,
            self.version,
            self.budget.stages,
            self.budget.remaining(),
        )
        try:
            async with asyncio.timeout(limits.timeout_seconds):
                function = ai_service.verify if stage == "verify" else ai_service.classify
                normalized = normalize_text(text, self.limits.max_candidates)
                variants = (
                    normalized.candidates[1:3] if normalized.flags and stage != "verify" else ()
                )
                result = await function(
                    text, self.context, variants, self.config, limits, policy=self.policy, **kwargs
                )
            runtime.failures.pop(self.provider, None)
            if getattr(result, "label", None) in self.disabled_labels:
                return ModerationResult(Label.REVIEW, 0, source="AI", reason="policy_mismatch")
            return result
        except (AIProcessingError, TimeoutError) as exc:
            runtime.metrics["ai_errors"] += 1
            if getattr(exc, "reason", "") not in {"budget_exhausted", "circuit_open"}:
                runtime.failed(
                    self.provider, self.limits.failure_limit, self.limits.cooldown_seconds
                )
            raise
        finally:
            logger.info(
                "Guard stage=%s finished elapsed=%.2fs requests=%d",
                stage,
                time.monotonic() - started,
                self.budget.requests,
            )

    async def run(self, original, *, draft=False):
        token = active_budget.set(self.budget)
        try:
            return await self.decide(original, draft=draft)
        except (AIProcessingError, TimeoutError) as exc:
            reason = (
                "budget_exhausted"
                if isinstance(exc, TimeoutError)
                and self.budget.seconds <= time.monotonic() - self.budget.started
                else getattr(
                    exc,
                    "reason",
                    "timeout" if isinstance(exc, TimeoutError) else "service_unavailable",
                )
            )
            return ModerationResult(Label.REVIEW, 0, source="UNAVAILABLE", reason=reason)
        finally:
            active_budget.reset(token)

    async def decide(self, original, *, draft):
        result = await self.call(
            "rewrite" if draft else "analyze", original, **({"rewrite": True} if draft else {})
        )
        if result.action == "REVIEW":
            runtime.metrics["automatic_rechecks"] += 1
            result = await self.call("rewrite", original, reconsider=True, rewrite=True)
        if result.action == "DROP":
            runtime.metrics["drop_audits"] += 1
            runtime.metrics["abuse_audits"] += result.label == Label.ABUSE
            first_label = result.label
            result = await self.call("drop_audit", original, audit_abuse=True)
            if result.action == "DROP":
                if result.label == first_label:
                    return result
                return ModerationResult(
                    Label.REVIEW, 0, source="AI", reason="conflicting_decisions"
                )
        if result.action != "PUBLISH":
            return result
        if draft and result.label != Label.REWRITE:
            return ModerationResult(Label.REVIEW, 0, source="AI", reason="rewrite_failed")
        for attempt in range(2):
            candidate = result.text if result.label == Label.REWRITE else original
            candidate = sanitize_text(candidate, remove_links=True, replacement=self.replacement)
            if not candidate.strip() or not publication_is_clean(
                candidate, replacement=self.replacement
            ):
                return ModerationResult(Label.REVIEW, 0, source="AI", reason="unsafe_output")
            runtime.metrics["rewrite_checks"] += result.label == Label.REWRITE
            verdict = await self.call("verify", candidate, verify_original=original)
            if not isinstance(verdict, Verification):
                raise AIRequestError("invalid_verification")
            if verdict.passed:
                runtime.metrics["verified_messages"] += 1
                return replace(result, text=candidate)
            logger.info(
                "Guard verification failed policy_pass=%s meaning_preserved=%s repairable=%s",
                verdict.policy_pass,
                verdict.meaning_preserved,
                verdict.repairable,
            )
            if attempt or not verdict.repairable:
                return ModerationResult(
                    Label.REVIEW,
                    0,
                    source="AI",
                    reason="meaning_changed" if not verdict.meaning_preserved else "rewrite_failed",
                )
            runtime.metrics["repair_attempts"] += 1
            result = await self.call(
                "repair",
                original,
                rewrite=True,
                feedback=verdict.issues,
                previous_candidate=candidate,
            )
            if result.label != Label.REWRITE:
                return ModerationResult(Label.REVIEW, 0, source="AI", reason="rewrite_failed")
