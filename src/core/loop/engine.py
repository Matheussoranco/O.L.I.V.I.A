from src.core.state.manager import Session, StateManager


class TurnResult:
    def __init__(
        self, content: str, tool_calls: list[dict] | None = None, status: str = "complete"
    ):
        self.content = content
        self.tool_calls = tool_calls or []
        self.status = status


class OliviaLoop:
    """
    The core execution loop of O.L.I.V.I.A.
    Inspired by Hermes' conversation_loop.py and turn_facade.py.
    """

    def __init__(self, state_manager: StateManager, provider):
        self.state = state_manager
        self.provider = provider
        self.max_iterations = 10

    async def run_turn(self, session_id: str, user_input: str) -> str:
        session = self.state.get_session(session_id)
        if not session:
            session = self.state.create_session()

        self.state.add_message(session_id, "user", user_input)

        iteration = 0
        while iteration < self.max_iterations:
            # 1. Context Assembly (Inspired by context_engine.py)
            context = self._assemble_context(session)

            # 2. LLM Call
            response = await self.provider.generate(context)

            # 3. Tool Dispatch (Inspired by tool_executor.py)
            if response.tool_calls:
                tool_results = await self._execute_tools(response.tool_calls, session_id)
                for res in tool_results:
                    self.state.add_message(session_id, "tool", res.content)
                iteration += 1
                continue

            # 4. Final Response
            self.state.add_message(session_id, "assistant", response.content)
            return response.content

        return "Max iterations reached without a final answer."

    def _assemble_context(self, session: Session):
        # Convert session messages to provider format
        return [vars(m) for m in session.messages]

    async def _execute_tools(self, tool_calls, session_id):
        # Placeholder for the actual tool dispatch logic
        results = []
        for call in tool_calls:
            # This will eventually call src.tools.executor
            results.append(TurnResult(content=f"Executed {call['name']}"))
        return results
