class CharmError(Exception):
    """Base class for custom charm errors."""


class CertificatesError(CharmError):
    """Error for tls certificates related operations."""
