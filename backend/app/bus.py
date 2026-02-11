from typing import Dict, Any, Type, Awaitable, Callable

class Bus:
    def __init__(self):
        self.handlers: Dict[Type, Callable[[Any, Any], Awaitable[Any]]] = {}

    def register(self, command_type: Type, handler: Callable[[Any, Any], Awaitable[Any]]):
        self.handlers[command_type] = handler

    async def execute(self, command: Any, *args, **kwargs):
        command_type = type(command)
        if command_type not in self.handlers:
            raise Exception(f"No handler registered for {command_type}")
        return await self.handlers[command_type](command, *args, **kwargs)

bus = Bus()
