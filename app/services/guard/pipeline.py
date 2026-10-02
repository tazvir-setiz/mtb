import asyncio
import hashlib
import logging
import time
from dataclasses import replace

from app.services import ai_service
from app.services.ai_policy import AIProcessingError
from app.services.ai_transport import AIRequestError
from app.services.grounding import GroundingService
from app.services.guard.budget import Budget, active_budget
from app.services.guard.contracts import (
    MeaningDecomposition,
    MeaningVerdict,
    PolicyVerdict,
    RewriteDraft,
)
from app.services.guard_models import Label, ModerationResult
from app.services.guard_runtime import runtime
from app.services.model_routing import RECOVERABLE, ModelRouter, fallback_attempt
from app.services.text_normalizer import normalize_text
from app.services.text_sanitizer import (
    publication_is_clean,
    sanitize_text,
    username_replacement,
)

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "4.2"


class GuardPipeline:
    def __init__(self, config, limits, context, policy, disabled_labels=(), grounding=None):
        self.disabled_labels = disabled_labels
        self.config = config
        self.limits = limits
        self.context = context
        self.policy = policy
        self.router = ModelRouter(config.model, config.fallback_model)
        self.grounding = grounding or GroundingService()
        self.grounding_attempted = False

        self.provider = hashlib.sha256(
            repr(
                (
                    config.base_url,
                    config.model,
                    config.api_key,
                )
            ).encode()
        ).hexdigest()

        self.version = hashlib.sha256((PIPELINE_VERSION + policy).encode()).hexdigest()[:12]

        self.replacement = username_replacement()

        self.budget = Budget(
            limits.total_timeout_seconds,
            limits.max_stages,
            limits.max_requests,
        )

    async def call(self, stage, text, *, escalation=None, **kwargs):
        model = self.router.escalate(escalation) if escalation else None
        if model:
            return await self._fallback(stage, text, model, **kwargs)
        try:
            return await self._call_once(stage, text, self.config, **kwargs)
        except (AIProcessingError, TimeoutError) as exc:
            reason = getattr(exc, "reason", "timeout" if isinstance(exc, TimeoutError) else "unknown")
            model = self.router.escalate(reason) if reason in RECOVERABLE else None
            if not model:
                raise
            return await self._fallback(stage, text, model, **kwargs)

    async def _fallback(self, stage, text, model, **kwargs):
        token = fallback_attempt.set(True)
        runtime.metrics["model_escalations"] += 1
        logger.info("Guard fallback model=%s reason=%s escalation_count=%d",
                    model, self.router.reason, self.router.escalations)
        try:
            return await self._call_once(stage, text, replace(self.config, model=model), **kwargs)
        finally:
            fallback_attempt.reset(token)

    async def _call_once(self, stage, text, config, **kwargs):
        self.budget.stage()

        provider = hashlib.sha256(repr((config.base_url, config.model, config.api_key)).encode()).hexdigest()
        if runtime.unavailable(provider):
            runtime.metrics["circuit_skips"] += 1
            raise AIRequestError("circuit_open")

        limits = replace(
            self.limits,
            timeout_seconds=min(
                self.limits.timeout_seconds,
                self.budget.remaining(),
            ),
        )

        runtime.metrics["ai_calls"] += 1
        runtime.metrics["fallback_model_calls" if config.model != self.config.model else "primary_model_calls"] += 1
        runtime.metrics[f"stage_{stage}"] += 1

        started = time.monotonic()

        try:
            async with asyncio.timeout(limits.timeout_seconds):
                normalized = normalize_text(
                    text,
                    self.limits.max_candidates,
                )

                variants = normalized.candidates[1:3] if normalized.flags else ()

                if stage in {"analyze", "reassess", "drop_audit"}:
                    result = await ai_service.classify(
                        text,
                        self.context,
                        variants,
                        config,
                        limits,
                        policy=self.policy,
                        **kwargs,
                    )

                elif stage == "meaning":
                    result = await ai_service.decompose_meaning(
                        text,
                        self.context,
                        variants,
                        config,
                        limits,
                        policy=self.policy,
                    )

                elif stage in {"rewrite", "repair"}:
                    decomposition = kwargs.pop("decomposition")

                    result = await ai_service.generate_rewrite(
                        text,
                        decomposition,
                        self.context,
                        config,
                        limits,
                        policy=self.policy,
                        **kwargs,
                    )

                elif stage == "policy_judge":
                    original = kwargs.pop("original")

                    result = await ai_service.judge_policy(
                        original,
                        text,
                        self.context,
                        config,
                        limits,
                        policy=self.policy,
                    )

                elif stage == "meaning_judge":
                    original = kwargs.pop("original")
                    decomposition = kwargs.pop("decomposition")

                    result = await ai_service.judge_meaning(
                        original,
                        text,
                        decomposition,
                        self.context,
                        config,
                        limits,
                        policy=self.policy,
                    )

                else:
                    raise AIRequestError("unknown_stage")

            runtime.failures.pop(provider, None)

            if getattr(result, "label", None) in self.disabled_labels:
                return ModerationResult(
                    Label.REVIEW,
                    0,
                    source="AI",
                    reason="policy_mismatch",
                )

            return result

        except (AIProcessingError, TimeoutError):
            runtime.failed(provider, self.limits.failure_limit, self.limits.cooldown_seconds)
            raise
        finally:
            logger.info(
                "Guard stage=%s elapsed=%.2fs requests=%d",
                stage,
                time.monotonic() - started,
                self.budget.requests,
            )

    async def run(self, original, *, draft=False):
        token = active_budget.set(self.budget)

        try:
            async with asyncio.timeout(self.budget.remaining()):
                return await self.decide(original, draft=draft)

        except (AIProcessingError, TimeoutError) as exc:
            reason = getattr(
                exc,
                "reason",
                "timeout",
            )

            return ModerationResult(
                Label.REVIEW,
                0,
                source="UNAVAILABLE",
                reason=reason,
            )

        finally:
            active_budget.reset(token)

    async def _ground(self, original, query):
        self.grounding_attempted = True
        runtime.metrics["grounding_attempts"] += 1
        if not self.config.news_grounding_enabled:
            return False
        result = await self.grounding.resolve(
            query, original, self.config.news_allowed_domains,
            timeout_seconds=min(8, self.budget.remaining()),
        )
        runtime.metrics[f"grounding_{result.status}"] += 1
        if not result.evidence:
            return False
        self.context = dict(self.context or {})
        self.context["news_evidence"] = [item.as_context() for item in result.evidence]
        return True

    async def _decompose(self, original):
        value = await self.call(
            "meaning",
            original,
        )

        if not isinstance(value, MeaningDecomposition):
            raise AIRequestError("invalid_meaning")

        return value

    async def _write(
        self,
        original,
        decomposition,
        *,
        feedback=(),
        previous_candidate=None,
    ):
        value = await self.call(
            "repair" if feedback else "rewrite",
            original,
            decomposition=decomposition,
            feedback=tuple(feedback),
            previous_candidate=previous_candidate,
            escalation="failed_rewrite_verification" if feedback else None,
        )

        if not isinstance(value, RewriteDraft):
            raise AIRequestError("invalid_rewrite")

        return value

    async def _judge(
        self,
        original,
        candidate,
        decomposition,
    ):
        policy_verdict = await self.call(
            "policy_judge",
            candidate,
            original=original,
        )

        meaning_verdict = await self.call(
            "meaning_judge",
            candidate,
            original=original,
            decomposition=decomposition,
        )

        if not isinstance(policy_verdict, PolicyVerdict) or not isinstance(
            meaning_verdict, MeaningVerdict
        ):
            raise AIRequestError("invalid_judge")

        return policy_verdict, meaning_verdict

    async def _rewrite_flow(
        self,
        original,
        decomposition,
    ):
        draft = await self._write(
            original,
            decomposition,
        )

        if not draft.success:
            return ModerationResult(
                Label.REVIEW,
                0,
                source="AI",
                reason="rewrite_failed",
            )

        candidate = sanitize_text(
            draft.text,
            remove_links=True,
            replacement=self.replacement,
        )

        if not candidate.strip() or not publication_is_clean(
            candidate,
            replacement=self.replacement,
        ):
            return ModerationResult(
                Label.REVIEW,
                0,
                source="AI",
                reason="unsafe_output",
            )

        policy_v, meaning_v = await self._judge(
            original,
            candidate,
            decomposition,
        )

        if policy_v.passed and meaning_v.passed:
            runtime.metrics["verified_messages"] += 1

            return ModerationResult(
                Label.REWRITE,
                1,
                candidate,
                "AI",
            )

        issues = tuple(policy_v.issues) + tuple(meaning_v.issues)

        runtime.metrics["repair_attempts"] += 1

        repaired = await self._write(
            original,
            decomposition,
            feedback=issues,
            previous_candidate=candidate,
        )

        if not repaired.success:
            return ModerationResult(
                Label.REVIEW,
                0,
                source="AI",
                reason="rewrite_failed",
            )

        candidate2 = sanitize_text(
            repaired.text,
            remove_links=True,
            replacement=self.replacement,
        )

        if not candidate2.strip() or not publication_is_clean(
            candidate2,
            replacement=self.replacement,
        ):
            return ModerationResult(
                Label.REVIEW,
                0,
                source="AI",
                reason="unsafe_output",
            )

        final_policy, final_meaning = await self._judge(
            original,
            candidate2,
            decomposition,
        )

        if final_policy.passed and final_meaning.passed:
            runtime.metrics["verified_messages"] += 1

            return ModerationResult(
                Label.REWRITE,
                1,
                candidate2,
                "AI",
            )

        reason = "meaning_changed" if not final_meaning.passed else "rewrite_failed"

        return ModerationResult(
            Label.REVIEW,
            0,
            source="AI",
            reason=reason,
        )

    async def decide(
        self,
        original,
        *,
        draft,
    ):
        if draft:
            decomposition = await self._decompose(original)

            if not decomposition.has_protected_meaning:
                return ModerationResult(
                    Label.REVIEW,
                    0,
                    source="AI",
                    reason="no_protected_meaning",
                )

            return await self._rewrite_flow(
                original,
                decomposition,
            )

        result = await self.call(
            "analyze",
            original,
        )

        if result.grounding_query and result.label in {Label.REVIEW, Label.REWRITE}:
            if not await self._ground(original, result.grounding_query):
                return ModerationResult(Label.REVIEW, 0, source="AI", reason="grounding_unresolved")
            result = await self.call("reassess", original, reconsider=True)

        if result.action == "REVIEW":
            runtime.metrics["automatic_rechecks"] += 1
            result = await self.call(
                "reassess", original, reconsider=True,
                escalation="unresolved_review" if result.label != Label.POLITICAL else None,
            )
            # A newly identified need must also be resolved before publication.
            if result.grounding_query and not self.grounding_attempted:
                if not await self._ground(original, result.grounding_query):
                    return ModerationResult(Label.REVIEW, 0, source="AI", reason="grounding_unresolved")
                result = await self.call("reassess", original, reconsider=True)

        if result.grounding_query:
            return ModerationResult(Label.REVIEW, 0, source="AI", reason="grounding_unresolved")

        if result.action == "DROP":
            first = result

            audited = await self.call(
                "drop_audit",
                original,
                audit_drop=True,
            )

            if audited.action != "DROP":
                result = audited

            elif audited.label != first.label:
                resolved = await self.call(
                    "drop_audit", original, audit_drop=True,
                    escalation="conflicting_drop_decisions",
                ) if self.router.escalations == 0 and self.router.fallback else None
                if resolved is None or resolved.label not in {first.label, audited.label}:
                    return ModerationResult(Label.REVIEW, 0, source="AI",
                                            reason="conflicting_drop_decisions")
                return resolved

            elif audited.label == Label.ABUSE:
                # هر دو classifier تأیید کرده‌اند که پیام فقط توهین است

                # و هیچ محتوای مستقل و قابل حفظی ندارد.

                if not getattr(first, "has_substance", False) and not getattr(
                    audited, "has_substance", False
                ):
                    return audited

                # حداقل یکی از classifierها تشخیص داده که علاوه بر توهین،

                # محتوای مستقلی برای حفظ کردن وجود دارد.

                decomposition = await self._decompose(original)

                if decomposition.has_protected_meaning:
                    return await self._rewrite_flow(
                        original,
                        decomposition,
                    )

                return audited

            else:
                return audited

        if result.label == Label.REWRITE:
            decomposition = await self._decompose(original)

            if decomposition.ambiguities:
                return ModerationResult(
                    Label.REVIEW,
                    0,
                    source="AI",
                    reason="ambiguous_meaning",
                )

            if not decomposition.has_protected_meaning:
                return ModerationResult(
                    Label.REVIEW,
                    0,
                    source="AI",
                    reason="no_protected_meaning",
                )

            return await self._rewrite_flow(
                original,
                decomposition,
            )

        if result.action != "PUBLISH":
            return result

        candidate = sanitize_text(
            original,
            remove_links=True,
            replacement=self.replacement,
        )

        if not candidate.strip() or not publication_is_clean(
            candidate,
            replacement=self.replacement,
        ):
            return ModerationResult(
                Label.REVIEW,
                0,
                source="AI",
                reason="unsafe_output",
            )

        return replace(
            result,
            text=candidate,
        )
