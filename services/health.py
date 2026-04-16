import asyncio
from datetime import datetime, timezone
import logging

from services.agents import AgentRecord

logger = logging.getLogger(__name__)


class AgentHealthMonitor:
    def __init__(self, database_module, agent_client, interval_seconds: float, timeout_seconds: float):
        self.database = database_module
        self.agent_client = agent_client
        self.interval_seconds = interval_seconds
        self.timeout_seconds = timeout_seconds
        self._status: dict[str, dict] = {}
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    async def start(self):
        try:
            await self.refresh_all()
        except Exception as exc:
            logger.warning("initial agent health refresh failed: %s", exc)
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._stopped.set()
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self):
        while not self._stopped.is_set():
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                try:
                    await self.refresh_all()
                except Exception as exc:
                    logger.warning("background agent health refresh failed: %s", exc)

    async def refresh_all(self):
        agents = await self.database.list_agents()
        tasks = [self.refresh_agent(dict(agent)) for agent in agents]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.warning("agent health task failed: %s", result)

    async def refresh_agent(self, agent: dict):
        try:
            reachable = await self.agent_client.health(
                AgentRecord(name=agent["name"], url=agent["url"]),
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            logger.warning("health check failed for agent %s: %s", agent["name"], exc)
            reachable = False

        previous = self._status.get(agent["name"], {})
        last_seen = previous.get("last_seen")
        if reachable:
            last_seen = datetime.now(timezone.utc).isoformat()
        self._status[agent["name"]] = {"reachable": reachable, "last_seen": last_seen}

    def status(self, agent_name: str) -> dict:
        return self._status.get(agent_name, {"reachable": False, "last_seen": None})

    def reachable_count(self) -> int:
        return sum(1 for item in self._status.values() if item.get("reachable"))
