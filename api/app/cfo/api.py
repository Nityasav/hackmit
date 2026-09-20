"""Independent CFO API. Live integration is injected, never inferred from fixtures."""

import asyncio
import importlib
import os
from threading import Lock
from dataclasses import dataclass, field

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from .demo import DemoData, ScriptedAuditor, ScriptedCFO, ScriptedSpecialist
from .engine import CFOEngine
from .model import StructuredCFOModel
from .ports import Auditor, DataSource, Specialist
from .repository import RunRepository
from .schemas import Run, RunRequest

router = APIRouter(prefix="/api/cfo", tags=["CFO orchestration"])
_runtime_lock = Lock()


@dataclass
class Adapters:
    data: DataSource
    specialists: dict[str, Specialist] = field(default_factory=dict)
    auditor: Auditor | None = None


class CFORuntime:
    def __init__(self, repository: RunRepository, adapters: Adapters | None = None):
        self.repository, self.adapters = repository, adapters
        self.pending: dict[str, asyncio.Task] = {}
        self.active_workspaces: set[str] = set()
        self.mutation_lock = Lock()
        repository.interrupt_pending()

    def start(self, request: RunRequest) -> Run:
        with self.mutation_lock:
            return self._start(request)

    def _start(self, request: RunRequest) -> Run:
        if request.workspace in self.active_workspaces:
            raise HTTPException(409, "A CFO run is already active for this workspace.")
        if len(self.pending) >= 2:
            raise HTTPException(429, "Two investigations are already running. Wait before starting another paid run.")
        if request.mode in {"scripted", "model_preview"}:
            if request.workspace != "sandbox":
                raise HTTPException(422, "The scripted harness supports sandbox only.")
            adapters = Adapters(DemoData(), {role: ScriptedSpecialist() for role in ["ap", "py", "gr"]}, ScriptedAuditor())
            model = ScriptedCFO()
        else:
            if self.adapters is None:
                raise HTTPException(503, "Live data/specialist adapters are not registered. Set CFO_ADAPTER_FACTORY; see app/cfo/README.md.")
            adapters = self.adapters
            if not {"ap", "py", "gr"}.issubset(adapters.specialists) or adapters.auditor is None:
                raise HTTPException(503, "Records are registered, but the ap, py, gr and auditor agents are not. "
                                         "Register them in the adapter factory; see app/cfo/README.md.")
            if any(adapters.auditor is agent for agent in adapters.specialists.values()):
                raise HTTPException(503, "The auditor must be a separate agent instance from the preparers.")
        if request.mode != "scripted":
            try:
                model = StructuredCFOModel.from_env()
            except ImportError:
                raise HTTPException(503, "Install CFO dependencies with uv sync --extra cfo.")
            except ValueError as exc:
                raise HTTPException(503, str(exc))
        engine = CFOEngine(adapters.data, adapters.specialists, adapters.auditor, model, self.repository)
        run = engine.create(request)
        self.active_workspaces.add(request.workspace)

        async def execute():
            try:
                await engine.execute(run)
            finally:
                self.active_workspaces.discard(request.workspace)
                self.pending.pop(run.id, None)
                if isinstance(model, StructuredCFOModel):
                    await model.close()

        self.pending[run.id] = asyncio.create_task(execute())
        return run.model_copy(deep=True)

    async def close(self):
        tasks = list(self.pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def runtime(request: Request) -> CFORuntime:
    # Both async run routes and synchronous dashboard readers initialize this.
    # Only one initialization may interrupt persisted pending runs.
    with _runtime_lock:
        return _runtime(request)


def _runtime(request: Request) -> CFORuntime:
    if not hasattr(request.app.state, "cfo_runtime"):
        adapters = None
        factory_path = os.getenv("CFO_ADAPTER_FACTORY", "app.integrations.cfo_factory:create_adapters")
        if factory_path:
            try:
                module_name, name = factory_path.split(":", 1)
                adapters = getattr(importlib.import_module(module_name), name)()
                if not isinstance(adapters, Adapters):
                    raise TypeError("Factory must return Adapters.")
            except Exception:
                raise HTTPException(503, "CFO_ADAPTER_FACTORY could not be loaded; check the server's integration configuration.")
        # Use the shared intake database by default. Tests and isolated CLI/demo
        # environments may still opt into a dedicated run database.
        repository = RunRepository(os.getenv("CFO_DB_PATH"))
        request.app.state.cfo_runtime = CFORuntime(repository, adapters)
    return request.app.state.cfo_runtime


@router.post("/runs", status_code=202, response_model=Run)
async def start_run(body: RunRequest, request: Request):
    return runtime(request).start(body)


@router.get("/runs/{run_id}", response_model=Run)
async def get_run(run_id: str, request: Request):
    try:
        return runtime(request).repository.get(run_id)
    except KeyError:
        raise HTTPException(404, "CFO run not found.")


@router.get("/runs/{run_id}/report", response_class=PlainTextResponse)
async def get_report(run_id: str, request: Request):
    run = await get_run(run_id, request)
    if not run.report_markdown:
        raise HTTPException(409, "The CFO has not published a report yet.")
    return PlainTextResponse(run.report_markdown, media_type="text/markdown")


@router.get("/workspaces/{workspace}/latest", response_model=Run)
async def latest_run(workspace: str, request: Request):
    run = runtime(request).repository.latest(workspace)
    if run is None:
        raise HTTPException(404, "No CFO run exists for this workspace.")
    return run
