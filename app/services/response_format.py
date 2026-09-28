import json
import re

from app.services.ai_policy import AIProcessingError


class OutputFormatError(AIProcessingError, ValueError):
    def __init__(self, detail):
        self.reason = "invalid_output"
        self.detail = detail
        super().__init__(detail)


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise OutputFormatError("duplicate_field")
        result[key] = value
    return result


def response_object(raw, maximum):
    if not isinstance(raw, str) or not raw.strip():
        raise OutputFormatError("empty_or_nontext_content")
    if len(raw) > maximum:
        raise OutputFormatError("response_too_long")
    fenced = re.fullmatch(r"\s*```(?:json)?\s*\n(.*?)\n```\s*", raw, re.S)
    try:
        data = json.loads(fenced.group(1) if fenced else raw, object_pairs_hook=unique_fields)
    except OutputFormatError:
        raise
    except (ValueError, RecursionError):
        raise OutputFormatError("invalid_json") from None
    if not isinstance(data, dict):
        raise OutputFormatError("expected_object")
    return data
