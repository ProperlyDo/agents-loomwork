class LoomError(Exception):
    """What stopped the work, with a code that tells one refusal from another."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
