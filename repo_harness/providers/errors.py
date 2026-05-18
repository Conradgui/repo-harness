"""Provider error shape shared by runtime engine and tests."""


class ProviderError(RuntimeError):
    def __init__(
        self,
        message,
        *,
        provider="",
        model="",
        base_url="",
        code="provider_error",
        http_status=None,
        retryable=False,
        attempts=1,
        retry_count=0,
    ):
        super().__init__(message)
        self.provider = str(provider)
        self.model = str(model)
        self.base_url = str(base_url)
        self.code = str(code or "provider_error")
        self.http_status = http_status
        self.retryable = bool(retryable)
        self.attempts = int(attempts or 1)
        self.retry_count = int(retry_count or 0)

    def to_metadata(self):
        return {
            "message": str(self),
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "code": self.code,
            "http_status": self.http_status,
            "retryable": self.retryable,
            "attempts": self.attempts,
            "retry_count": self.retry_count,
        }
