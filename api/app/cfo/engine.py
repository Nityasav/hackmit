"""Bounded orchestrator/workers + independent evaluator loop.

Only this coordinator changes run state. Collaborators receive copies and a
read-only tool gateway, never the repository or financial approval capability.
"""

import asyncio
from collections import Counter
from uuid import uuid4

from .ports import Auditor, CFOModel, DataSource, Specialist
from .reporting import render, validate_narrative
from .repository import RunRepository
from .schemas import AcceptedClaim, Event, FollowUp, Narrative, Plan, Review, Run, RunRequest, TaskSpec, TaskState, WorkerResult
from .tools import BoundaryError, EvidenceTools


class CFOEngine:
    def __init__(self, data: DataSource, specialists: dict[str, Specialist], auditor: Auditor,
                 model: CFOModel, repository: RunRepository):
        self.data, self.specialists, self.auditor = data, specialists, auditor
        self.model, self.repository = model, repository
        if any(auditor is agent for agent in specialists.values()):
            raise ValueError("Auditor must be independent of specialist instances.")

    def create(self, request: RunRequest) -> Run:
        run = Run(id="CFO-" + uuid4().hex[:12], request=request, model_label=self.model.label)
        self.repository.save(run)
        return run

    async def execute(self, run: Run) -> Run:
        if run.status != "queued":
            raise ValueError("Only a queued run can execute; start a new run to retry.")

        def emit(actor, action, detail, task_id=None, references=None):
            run.events.append(Event(actor=actor, action=action, detail=detail,
                                    task_id=task_id, references=references or []))
            self.repository.save(run)

        async def call_model(action, invoke, schema):
            if run.model_calls >= run.request.limits.max_model_calls:
                raise BoundaryError("CFO model call budget exhausted.")
            run.model_calls += 1
            emit("cfo", action + ".started", "Bounded model request.")
            result = schema.model_validate(await asyncio.wait_for(invoke(), run.request.limits.call_timeout_s))
            emit("cfo", action + ".completed", result.model_dump_json())
            return result

        try:
            run.status = "planning"
            emit("cfo", "snapshot.started", "Load authorized source inventory and accounting scope.")
            run.scope = await asyncio.wait_for(self.data.snapshot(run.request.workspace), run.request.limits.call_timeout_s)
            if run.scope.workspace != run.request.workspace:
                raise BoundaryError("Workspace mismatch in source inventory.")
            if not all([run.scope.snapshot_id, run.scope.institution, run.scope.period, run.scope.accounting_profile]):
                raise BoundaryError("Incomplete accounting scope.")
            if len({s.id for s in run.scope.sources}) != len(run.scope.sources):
                raise BoundaryError("Source IDs must be unique in a snapshot.")
            if len({c.id for c in run.scope.calculations}) != len(run.scope.calculations):
                raise BoundaryError("Calculation IDs must be unique in a snapshot.")
            if any(not set(c.source_ids).issubset({s.id for s in run.scope.sources}) for c in run.scope.calculations):
                raise BoundaryError("Calculation inventory references unavailable sources.")
            run.unresolved.extend(run.scope.gaps)
            objective = run.request.objective
            if run.request.workflow == "five_agent":
                objective += "\nFive-agent workflow: delegate independent tasks to ALL of ap, py and gr, including evidence-gap checks. Auditor review is automatic."
            plan = await call_model("plan", lambda: self.model.plan(objective, run.scope.model_copy(deep=True)), Plan)
            if run.request.workflow == "five_agent":
                # A model cannot silently omit a required domain. Added tasks remain
                # subject to the same scope, DAG and task-budget checks below.
                for role in ("ap", "py", "gr"):
                    if not any(task.role == role for task in plan.tasks):
                        task_id = "coverage-" + role
                        while any(task.id == task_id for task in plan.tasks):
                            task_id += "-x"
                        plan.tasks.append(TaskSpec(id=task_id, role=role,
                            objective=f"Review {role} evidence relevant to the objective; explicitly identify missing support.",
                            source_ids=[s.id for s in run.scope.sources if s.domain in {role, "shared"}],
                            success_criteria="Return supported cited observations or explicit evidence requests; never invent amounts."))
                        emit("cfo", "plan.coverage_added", role)
            self._validate_plan(plan, run)
            run.plan = plan
            run.tasks = [TaskState(spec=spec) for spec in plan.tasks]
            run.status = "running"
            emit("cfo", "plan.accepted", plan.rationale)

            while any(t.status == "queued" for t in run.tasks):
                states = {t.spec.id: t for t in run.tasks}
                ready = []
                for task in run.tasks:
                    if task.status != "queued":
                        continue
                    dependencies = [states[d] for d in task.spec.depends_on]
                    if any(d.status in {"failed", "needs_evidence", "blocked"} for d in dependencies):
                        task.status = "blocked"
                        run.unresolved.append(f"{task.spec.id}: dependency did not complete successfully.")
                        emit("cfo", "task.blocked", "Upstream work is unresolved.", task.spec.id)
                    elif all(d.status == "done" for d in dependencies):
                        ready.append(task)
                if not ready:
                    break
                ready.sort(key=lambda t: (t.spec.priority, t.spec.id))
                # Launch at most two independent tasks; deterministic incorporation order.
                batch = ready[:run.request.limits.concurrency]
                results = await asyncio.gather(*[
                    self._investigate(run, task, states, emit, call_model) for task in batch
                ])
                for accepted in results:
                    run.accepted.extend(accepted)

            self._deduplicate(run)
            current = await asyncio.wait_for(self.data.snapshot(run.request.workspace), run.request.limits.call_timeout_s)
            if current.snapshot_id != run.scope.snapshot_id:
                run.status = "stale"
                run.accepted.clear()
                run.unresolved.append("Source snapshot changed during investigation; rerun before publishing conclusions.")
            elif any(t.status in {"failed", "blocked"} for t in run.tasks):
                run.status = "partial"
            elif run.unresolved:
                run.status = "needs_evidence"
            else:
                run.status = "completed"

            narrative = None
            if run.accepted:
                try:
                    narrative = await call_model("synthesize", lambda: self.model.synthesize(run.model_copy(deep=True)), Narrative)
                    validate_narrative(narrative, run)
                except Exception as exc:
                    narrative = None
                    run.unresolved.append(f"CFO narrative unavailable ({type(exc).__name__}); using reviewed findings verbatim.")
                    if run.status == "completed":
                        run.status = "partial"
                    emit("cfo", "synthesis.fallback", "Invalid or unavailable narrative; deterministic report preserved.")
            # Recheck after the potentially slow model synthesis too.
            current = await asyncio.wait_for(self.data.snapshot(run.request.workspace), run.request.limits.call_timeout_s)
            if current.snapshot_id != run.scope.snapshot_id:
                run.status = "stale"
                run.accepted.clear()
                narrative = None
                if not any("Source snapshot changed" in item for item in run.unresolved):
                    run.unresolved.append("Source snapshot changed before report publication; rerun the investigation.")
            run.cfo_input_tokens = getattr(self.model, "input_tokens", 0)
            run.cfo_output_tokens = getattr(self.model, "output_tokens", 0)
            render(run, narrative)
            emit("cfo", "report.published", f"Report status: {run.status}; no financial changes applied.")
        except asyncio.CancelledError:
            run.status = "interrupted"
            run.unresolved.append("Run cancelled or server stopping. Start a new run to retry.")
            render(run)
            emit("cfo", "run.interrupted", "Execution interrupted.")
            raise
        except Exception as exc:
            run.status = "failed"
            # Do not expose provider error bodies, credentials, or raw source contents.
            run.unresolved.append(f"Run stopped ({type(exc).__name__}). Check adapter configuration and server diagnostics.")
            render(run)
            emit("cfo", "run.failed", run.unresolved[-1])
        return run

    def _validate_plan(self, plan: Plan, run: Run):
        if len(plan.tasks) > run.request.limits.max_tasks:
            raise BoundaryError("Plan exceeds task budget.")
        ids = [t.id for t in plan.tasks]
        if len(set(ids)) != len(ids):
            raise BoundaryError("Duplicate task IDs.")
        allowed = {s.id for s in run.scope.sources}
        for task in plan.tasks:
            if task.role not in self.specialists:
                raise BoundaryError("Requested specialist adapter is not registered.")
            if not set(task.source_ids).issubset(allowed):
                raise BoundaryError("Plan cites unknown source IDs.")
            if not set(task.depends_on).issubset(set(ids)) or task.id in task.depends_on:
                raise BoundaryError("Invalid task dependency.")
        remaining = {t.id: set(t.depends_on) for t in plan.tasks}
        resolved = set()
        while remaining:
            ready = {key for key, deps in remaining.items() if deps.issubset(resolved)}
            if not ready:
                raise BoundaryError("Task dependency graph contains a cycle.")
            resolved.update(ready)
            remaining = {key: deps for key, deps in remaining.items() if key not in ready}

    async def _investigate(self, run, task, states, emit, call_model):
        accepted = []
        feedback = None
        timeout = run.request.limits.call_timeout_s
        scope = run.scope.model_copy(deep=True)
        # Inventory is scoped too, not just tool authorization.
        scope.sources = [s for s in scope.sources if s.id in task.spec.source_ids]
        scope.calculations = [c for c in scope.calculations if set(c.source_ids).issubset(task.spec.source_ids)]
        dependencies = [states[d].result.model_copy(deep=True) for d in task.spec.depends_on if states[d].result]
        try:
            for attempt in range(run.request.limits.review_cycles):
                task.attempts += 1
                task.status = "working"
                tools = EvidenceTools(self.data, scope, run, task, task.spec.role, emit, task.spec.source_ids)
                emit("cfo", "delegate", feedback or task.spec.objective, task.spec.id, task.spec.source_ids)
                result = WorkerResult.model_validate(await asyncio.wait_for(
                    self.specialists[task.spec.role].investigate(task.spec.model_copy(deep=True), scope.model_copy(deep=True), tools, dependencies, feedback), timeout))
                task.result = result
                emit(task.spec.role, "result.submitted", result.model_dump_json(), task.spec.id)
                if result.evidence_requests:
                    run.unresolved.extend(f"{task.spec.id}: {request}" for request in result.evidence_requests)
                if not result.claims:
                    task.status = "needs_evidence"
                    if not result.evidence_requests:
                        run.unresolved.append(f"{task.spec.id}: no reviewable conclusions returned.")
                    break
                if len({c.id for c in result.claims}) != len(result.claims):
                    raise BoundaryError("Duplicate claim IDs within specialist response.")
                attempt_accepted = []
                challenges = []
                for claim in result.claims:
                    calculation = tools.validate_claim(claim)
                    task.status = "auditor_review"
                    review_tools = EvidenceTools(self.data, scope, run, task, "au", emit, task.spec.source_ids)
                    emit("cfo", "review.requested", claim.id, task.spec.id, claim.evidence_ids)
                    review = Review.model_validate(await asyncio.wait_for(
                        self.auditor.review(claim.model_copy(deep=True), scope.model_copy(deep=True), review_tools), timeout))
                    if review.verdict == "accept":
                        checked = review_tools.validate_claim(claim)
                        if checked != calculation:
                            raise BoundaryError("Auditor calculation disagrees with preparer's calculation.")
                        attempt_accepted.append(AcceptedClaim(task_id=task.spec.id, role=task.spec.role,
                                                            claim=claim, review=review, calculation=calculation))
                    else:
                        challenges.append((claim, review))
                    emit("au", "review." + review.verdict, review.rationale + " " + review.required_action, task.spec.id, [claim.id])
                accepted = attempt_accepted
                if not challenges:
                    task.status = "needs_evidence" if result.evidence_requests else "done"
                    break
                if attempt + 1 >= run.request.limits.review_cycles:
                    run.unresolved.extend(f"{claim.id}: {review.rationale} Required: {review.required_action}" for claim, review in challenges)
                    task.status = "needs_evidence"
                    break
                instructions = []
                can_retry = True
                for claim, review in challenges:
                    follow = await call_model("follow_up", lambda c=claim, r=review: self.model.follow_up(task.spec.model_copy(deep=True), c.model_copy(deep=True), r.model_copy(deep=True)), FollowUp)
                    if follow.action != "retry":
                        can_retry = False
                        run.unresolved.append(f"{claim.id}: {follow.instruction}")
                    instructions.append(f"{claim.id}: {review.required_action}; CFO: {follow.instruction}")
                if not can_retry:
                    task.status = "needs_evidence"
                    break
                feedback = "\n".join(instructions) + "\nReturn the complete revised task result, preserving supported conclusions."
                # No candidate from a superseded attempt may silently survive.
                accepted = []
            emit("cfo", "task.finished", task.status, task.spec.id)
        except Exception as exc:
            task.status = "failed"
            run.unresolved.append(f"{task.spec.id}: {type(exc).__name__}; task stopped without accepting unchecked claims.")
            emit("cfo", "task.failed", run.unresolved[-1], task.spec.id)
            accepted = []
        return accepted

    @staticmethod
    def _deduplicate(run):
        groups = {}
        duplicate_ids = {key for key, count in Counter(a.claim.id for a in run.accepted).items() if count > 1}
        for accepted in run.accepted:
            groups.setdefault(accepted.claim.event_key, []).append(accepted)
        retained = []
        for event_key, items in groups.items():
            signatures = {(a.claim.disposition, a.claim.conclusion, a.claim.proposed_action,
                           a.calculation.model_dump_json() if a.calculation else None) for a in items}
            if len(signatures) > 1 or any(a.claim.id in duplicate_ids for a in items):
                run.unresolved.append(f"Conflicting or ambiguous claims for {event_key}: " + ", ".join(a.claim.id for a in items))
            else:
                retained.append(items[0])
        run.accepted = retained
