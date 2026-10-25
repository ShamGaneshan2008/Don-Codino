"""Bounded asynchronous subprocess execution, cancellation, and tree cleanup."""

import asyncio
import contextlib
import os
import signal
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

OUTPUT_LIMIT = 256_000


@dataclass
class Result:
    code: int
    output: str
    stdout: str = ""
    stderr: str = ""
    started_at: str = ""
    ended_at: str = ""


async def stop(process):
    if process.returncode is not None:
        return
    if os.name == "nt":
        killer = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(process.pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(killer.wait(), timeout=5)
        except TimeoutError:
            killer.kill()
            await killer.wait()
        # Restricted Windows accounts can deny taskkill's process enumeration.
        # Always terminate the direct child as well, so cleanup cannot hang.
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    await process.wait()


async def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 30,
    cancel: asyncio.Event | None = None,
    emit=None,
    data: bytes | None = None,
    env: dict | None = None,
) -> Result:
    options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {
            "start_new_session": True,
        }
    )
    started_at = datetime.now(UTC).isoformat()
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **options,
    )
    output = bytearray()
    stdout, stderr = bytearray(), bytearray()
    truncated = False

    async def consume(stream, separate):
        nonlocal truncated
        pending = bytearray()
        while chunk := await stream.read(4096):
            remaining = OUTPUT_LIMIT - len(output)
            output.extend(chunk[:remaining])
            separate.extend(chunk[:remaining])
            # Emit complete lines so secrets split across pipe reads are redacted together.
            if emit and remaining > 0:
                pending.extend(chunk[:remaining])
                while b"\n" in pending:
                    line, _, rest = pending.partition(b"\n")
                    pending = bytearray(rest)
                    emit(line.rstrip(b"\r").decode("utf-8", errors="replace"))
            if len(chunk) > remaining:
                truncated = True
        if emit and pending and not truncated:
            emit(pending.decode("utf-8", errors="replace"))
        if emit and truncated:
            emit("[Output truncated at 256 KB; incomplete final line omitted]")

    async def feed():
        try:
            if data:
                process.stdin.write(data)
                await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            process.stdin.close()

    async def communicate():
        await asyncio.gather(
            consume(process.stdout, stdout), consume(process.stderr, stderr), feed(), process.wait()
        )

    io = asyncio.create_task(communicate())
    cancelled = asyncio.create_task(cancel.wait()) if cancel else None
    try:
        done, _ = await asyncio.wait(
            [io, *([cancelled] if cancelled else [])],
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if cancelled and cancelled in done:
            raise asyncio.CancelledError
        if io not in done:
            raise TimeoutError(f"Process exceeded {timeout} seconds")
        await io
    finally:
        await stop(process)
        if cancelled:
            cancelled.cancel()
        if not io.done():
            io.cancel()
        await asyncio.gather(io, *([cancelled] if cancelled else []), return_exceptions=True)
    suffix = "\n[Output truncated at 256 KB]" if truncated else ""
    return Result(
        process.returncode,
        output.decode("utf-8", errors="replace") + suffix,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
        started_at,
        datetime.now(UTC).isoformat(),
    )
