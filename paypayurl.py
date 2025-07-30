# paypayurl.py
import time
import logging
from typing import Optional
from PayPaython_mobile import PayPay, PayPayLoginError

logger = logging.getLogger("PayPayLinkHandler")


def linkpays(paypay: PayPay, link: str, password: str = "") -> Optional[dict]:
    """
    PayPayリンクによる支払いを処理する。
    
    Args:
        paypay (PayPay): 認証済みPayPayインスタンス。
        link (str): 支払いリンク。
        password (str, optional): リンクに設定されたパスワード。未設定なら空文字。

    Returns:
        dict or None: 決済結果オブジェクト、失敗時は例外を投げる。
    
    Raises:
        ValueError: 無効なリンク、状態不一致、パスワード不足など。
        PayPayLoginError: トークン切れ。
        RuntimeError: その他予期せぬエラー。
    """
    try:
        link_info = paypay.link_check(link)
        
        if not link_info or not hasattr(link_info, "status"):
            raise ValueError("無効なリンクです")
        
        if link_info.status not in ["PENDING", "ACTIVE"]:
            raise ValueError(f"リンク状態が異常です: {link_info.status}")
        
        if getattr(link_info, "has_password", False) and not password:
            raise ValueError("パスワードが必要なリンクです")
        
        result = paypay.link_receive(link, password, link_info=link_info)
        return result
    
    except PayPayLoginError as e:
        raise PayPayLoginError("アクセストークンが無効です。再認証してください。") from e
    
    except Exception as e:
        logger.exception("linkpays 処理中の予期せぬエラー")
        raise RuntimeError(f"送金処理に失敗しました: {e}") from e
