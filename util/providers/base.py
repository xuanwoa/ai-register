from abc import ABC, abstractmethod


class MailProviderError(Exception):
    """邮箱 provider 统一异常类型。"""


class MailProvider(ABC):
    """邮箱 provider 抽象接口。"""

    name = "base"

    @abstractmethod
    def create_temp_email(self):
        """创建临时邮箱，返回 (email, password, mail_token)。"""

    @abstractmethod
    def fetch_emails(self, mail_token):
        """获取邮件列表。"""

    @abstractmethod
    def fetch_email_detail(self, mail_token, msg_id):
        """获取单封邮件详情。"""
