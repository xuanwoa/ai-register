from register.providers.base import ModelProvider, ModelProviderError


class OpenAIModelProvider(ModelProvider):
    name = "openai"

    def __init__(self, enable_oauth=True, oauth_required=True, oauth_issuer="", oauth_client_id="", oauth_redirect_uri=""):
        self._enable_oauth = bool(enable_oauth)
        self._oauth_required = bool(oauth_required)
        self._oauth_issuer = str(oauth_issuer or "").strip()
        self._oauth_client_id = str(oauth_client_id or "").strip()
        self._oauth_redirect_uri = str(oauth_redirect_uri or "").strip()

        if not self._oauth_issuer:
            raise ModelProviderError("providers.openai.oauth_issuer 未配置")
        if not self._oauth_client_id:
            raise ModelProviderError("providers.openai.oauth_client_id 未配置")
        if not self._oauth_redirect_uri:
            raise ModelProviderError("providers.openai.oauth_redirect_uri 未配置")

    def oauth_enabled(self):
        return self._enable_oauth

    def oauth_required(self):
        return self._oauth_required

    def oauth_issuer(self):
        return self._oauth_issuer

    def oauth_client_id(self):
        return self._oauth_client_id

    def oauth_redirect_uri(self):
        return self._oauth_redirect_uri
