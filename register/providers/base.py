from abc import ABC, abstractmethod


class ModelProviderError(Exception):
    """模型 provider 统一异常类型。"""


class ModelProvider(ABC):
    """模型 provider 抽象接口。"""

    name = "base"

    @abstractmethod
    def oauth_enabled(self):
        """是否启用 OAuth 流程。"""

    @abstractmethod
    def oauth_required(self):
        """OAuth 失败时是否中断流程。"""

    @abstractmethod
    def oauth_issuer(self):
        """OAuth issuer 地址。"""

    @abstractmethod
    def oauth_client_id(self):
        """OAuth client_id。"""

    @abstractmethod
    def oauth_redirect_uri(self):
        """OAuth redirect_uri。"""
