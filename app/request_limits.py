"""Bound JSON mutations before buffering them; correlate responses without logging payloads."""

from uuid import uuid4

from starlette.responses import JSONResponse


class RequestLimits:
    def __init__(self, app, limit=128000):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid4().hex

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        if scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send_with_id)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            size += len(body)
            if size > self.limit:
                response = JSONResponse(
                    {"detail": "Request body exceeds 128 KB", "request_id": request_id},
                    status_code=413,
                )
                return await response(scope, receive, send_with_id)
            chunks.append(body)
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        return await self.app(scope, bounded_receive, send_with_id)
