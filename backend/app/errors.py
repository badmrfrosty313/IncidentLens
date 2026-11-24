"""Domain errors. The HTTP layer maps these to status codes; analysis code never imports HTTP."""

from __future__ import annotations


class IncidentLensError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class EmptyInputError(IncidentLensError):
    status_code = 422
    code = "empty_input"


class InvalidInputError(IncidentLensError):
    status_code = 422
    code = "invalid_input"


class InputTooLargeError(IncidentLensError):
    status_code = 413
    code = "input_too_large"


class TooManyEventsError(InputTooLargeError):
    code = "too_many_events"


class UnknownScenarioError(IncidentLensError):
    status_code = 404
    code = "unknown_scenario"
