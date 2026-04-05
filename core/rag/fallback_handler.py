from core.interfaces.fallback_handler import BaseFallbackHandler

_MESSAGES = {
    "low_confidence": "抱歉，我对这个问题没有足够把握，建议联系人工客服。",
    "out_of_scope": "这个问题超出了我的服务范围，请联系人工客服。",
    "error": "系统暂时出现问题，请稍后重试。",
}

_DEFAULT_MESSAGE = "抱歉，暂时无法处理您的请求，请联系人工客服。"


class TellUserFallbackHandler(BaseFallbackHandler):
    """Returns a canned message based on the fallback reason."""

    async def handle(self, question: str, session_id: str, reason: str) -> str:
        return _MESSAGES.get(reason, _DEFAULT_MESSAGE)
