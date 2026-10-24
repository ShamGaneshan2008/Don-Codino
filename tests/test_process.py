import asyncio
import sys

import pytest

from app.process import run


def test_actual_subprocess_captures_exit_and_output():
    result = asyncio.run(run([sys.executable, "-c", "import sys; print('actual'); sys.exit(3)"]))
    assert result.code == 3
    assert result.output.strip() == "actual"


def test_timeout_terminates_process():
    with pytest.raises(TimeoutError):
        asyncio.run(run([sys.executable, "-c", "import time; time.sleep(60)"], timeout=1))


def test_actual_subprocess_cancellation():
    async def scenario():
        cancel = asyncio.Event()
        task = asyncio.create_task(
            run([sys.executable, "-c", "import time; time.sleep(60)"], cancel=cancel)
        )
        await asyncio.sleep(0.1)
        cancel.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


def test_streaming_keeps_split_secrets_in_one_event():
    events = []
    code = (
        "import sys,time; sys.stdout.write('token=super'); sys.stdout.flush(); "
        "time.sleep(0.1); print('secret')"
    )
    asyncio.run(run([sys.executable, "-c", code], emit=events.append))
    assert events == ["token=supersecret"]
