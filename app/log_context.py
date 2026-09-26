import inspect
import logging
from contextvars import ContextVar
from functools import wraps

context = ContextVar("log_context", default={})


class ContextFilter(logging.Filter):
    def filter(self, record):
        record.trace = " ".join(f"{key}={value}" for key, value in context.get().items()) or "-"
        return True


def traced(function):
    signature = inspect.signature(function)

    @wraps(function)
    async def wrapped(*args, **kwargs):
        arguments = signature.bind(*args, **kwargs).arguments
        values = dict(context.get())
        for key in ("job_id", "source_id", "destination_id", "msg_id"):
            if key in arguments:
                values[key] = arguments[key]
        for key in ("original", "event"):
            if key in arguments:
                message = arguments[key]
                if key == "event":
                    message = message.message
                values["msg_id"] = getattr(message, "id", None)
        token = context.set(values)
        try:
            return await function(*args, **kwargs)
        finally:
            context.reset(token)

    return wrapped
