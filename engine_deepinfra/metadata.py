"""Identity constants. Standard library only.

The TUI imports this module, not ``engine.py``, so reading the provider's
display name never pulls in the provider's SDK.
"""

PROVIDER_NAME = "DeepInfra"
PROVIDER_HOMEPAGE = "https://deepinfra.com"
PLATFORM = "deepinfra"
API_KEY_ENV_VAR = "DEEPINFRA_API_KEY"
API_KEY_PATTERN = r".+"
