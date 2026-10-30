class EventError(Exception):
    """A rule violation or bad input, mapped to an HTTP status by the API.

    Core services raise it too (e.g. confirming an expired entry), so they stay
    independent of the web layer while still producing a clean 4xx.
    """

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status
