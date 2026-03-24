"""
alerter.py
==========
이메일 알림 모듈 (체결 완료, 서킷브레이커 발동, 오류 시 자동 발송)

[SecurityAuditor]
  - SMTP 비밀번호는 config.py 경유 (Gmail 앱 비밀번호 사용)
  - 로그에 비밀번호 출력 금지
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, RECIPIENT_EMAIL

logger = logging.getLogger(__name__)


class Alerter:
    """
    이메일 알림 발송기.

    Args:
        enabled: False면 모든 알림을 무시 (개발/테스트용)
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._configured = bool(SMTP_USER and SMTP_PASS and RECIPIENT_EMAIL)

        if enabled and not self._configured:
            logger.warning(
                "[Alerter] SMTP 설정이 .env에 없습니다. 알림이 비활성화됩니다. "
                "SMTP_USER, SMTP_PASS, RECIPIENT_EMAIL을 .env에 등록하세요."
            )

    def send(self, subject: str, body: str) -> bool:
        """
        이메일 발송.

        Args:
            subject: 제목 (예: "[HFT] ETH 차익거래 체결 완료")
            body: 본문 (HTML 또는 텍스트)

        Returns:
            성공 여부
        """
        if not self.enabled or not self._configured:
            logger.info(f"[Alerter][SKIP] {subject}")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = SMTP_USER
            msg["To"] = RECIPIENT_EMAIL
            msg.attach(MIMEText(body, "html"))

            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_USER, RECIPIENT_EMAIL, msg.as_string())

            logger.info(f"[Alerter] 이메일 발송 완료: {subject}")
            return True

        except Exception as e:
            logger.error(f"[Alerter] 이메일 발송 실패: {e}")
            return False

    def notify_trade_filled(self, symbol: str, side: str, amount_krw: float, premium_pct: float):
        """체결 완료 알림."""
        subject = f"[HFT] {symbol} {side} 체결 완료 (+{premium_pct:.2f}%)"
        body = f"""
        <h2>HFT 차익거래 체결 완료</h2>
        <table>
          <tr><td><b>종목</b></td><td>{symbol}</td></tr>
          <tr><td><b>방향</b></td><td>{side}</td></tr>
          <tr><td><b>금액</b></td><td>{amount_krw:,.0f}원</td></tr>
          <tr><td><b>김치 프리미엄</b></td><td>+{premium_pct:.2f}%</td></tr>
        </table>
        """
        self.send(subject, body)

    def notify_circuit_breaker(self, reason: str, daily_pnl_pct: float):
        """서킷브레이커 발동 알림 (즉시 확인 필요)."""
        subject = f"[HFT] 서킷브레이커 발동! 오늘 PnL: {daily_pnl_pct:.2f}%"
        body = f"""
        <h2 style="color:red;">서킷브레이커 발동</h2>
        <p><b>사유:</b> {reason}</p>
        <p><b>오늘 누적 PnL:</b> {daily_pnl_pct:.2f}%</p>
        <p>엔진이 일시 정지되었습니다. 직접 확인 후 재가동이 필요합니다.</p>
        """
        self.send(subject, body)

    def notify_error(self, error_msg: str):
        """예외 오류 알림."""
        subject = "[HFT] 엔진 오류 발생 - 확인 필요"
        body = f"<h2>오류 발생</h2><pre>{error_msg}</pre>"
        self.send(subject, body)
