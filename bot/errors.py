class BotError(Exception):
    """Base class."""


class TransientError(BotError):
    """Worth retrying: timeouts, 5xx pages, dropped connections."""


class PermanentError(BotError):
    """Retrying cannot help: bad credentials, validation errors, wrong confirmation."""


class VerificationError(PermanentError):
    """The run finished but the confirmation did not match what was submitted."""


class StepFailed(BotError):
    def __init__(self, step: str, attempts: int, cause: Exception, permanent: bool):
        kind = "permanent error" if permanent else f"gave up after {attempts} attempts"
        super().__init__(f"step '{step}' failed ({kind}): {cause}")
        self.step, self.attempts, self.cause, self.permanent = step, attempts, cause, permanent
