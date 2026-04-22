"""Typed provider client exceptions."""


class ProviderError(Exception):
    """Base exception for provider client failures."""


class ProviderConfigError(ProviderError):
    """Raised when provider client configuration is invalid."""


class ProviderRequestError(ProviderError):
    """Raised when an HTTP request fails before a valid provider payload is returned."""


class ProviderResponseError(ProviderError):
    """Raised when provider returns an explicit error response."""


class ProviderRateLimitError(ProviderResponseError):
    """Raised when provider returns a rate-limit response."""


class ProviderQuotaExceededError(ProviderRateLimitError):
    """Raised when local quota guard blocks a request before outbound send."""


class ProviderSchemaError(ProviderError):
    """Raised when provider payload is not in expected JSON object format."""
