"""Small framed-pipe client used only inside the CSV runner image."""

import asyncio
import threading

from .protocol import encode, read


class SDK:
    def __init__(self, incoming, outgoing, limit):
        self.incoming, self.outgoing, self.limit = incoming, outgoing, limit
        self.loop = asyncio.get_running_loop()
        self.pending = {}
        self.next_id = 0
        self.finished = self.loop.create_future()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _send(self, value):
        self.outgoing.write(encode(value, self.limit))
        self.outgoing.flush()

    def _read(self):
        try:
            while True:
                packet = read(self.incoming, self.limit)
                self.loop.call_soon_threadsafe(self._receive, packet)
                if packet.get("type") in {"finished", "abort"}:
                    return
        except BaseException as exc:
            self.loop.call_soon_threadsafe(self._abort, str(exc))

    def _abort(self, message):
        for future in [*self.pending.values(), self.finished]:
            if not future.done():
                future.set_exception(RuntimeError(message))

    def _receive(self, packet):
        if packet.get("type") == "finished":
            if not self.finished.done():
                self.finished.set_result(None)
        elif packet.get("type") == "reply" and packet.get("id") in self.pending:
            future = self.pending.pop(packet["id"])
            if not future.done():
                future.set_result(packet["result"])
        else:
            self._abort(packet.get("message", "Host closed the tool gate."))

    async def call(self, subtask_id, arguments, *, handles=None):
        self.next_id += 1
        request_id = str(self.next_id)
        future = self.loop.create_future()
        self.pending[request_id] = future
        self._send(
            {
                "type": "call",
                "id": request_id,
                "subtask_id": subtask_id,
                "arguments": arguments,
                "handles": [] if handles is None else handles,
            }
        )
        return await future

    async def parallel(self, *calls):
        return await asyncio.gather(*calls)

    async def finish(self, packet):
        self._send(packet)
        await self.finished
        self.reader.join(timeout=1)
