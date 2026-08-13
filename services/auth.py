"""Small, deployable shared-secret guard for the Streamlit surface."""

import hmac


def access_granted(candidate: str, configured_token: str) -> bool:
    """Fail closed and compare tokens without content-dependent timing."""
    if not candidate or not configured_token:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), configured_token.encode("utf-8"))
