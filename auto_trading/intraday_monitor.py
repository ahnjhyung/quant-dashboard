"""
Intraday Monitor
================
- Role: Fast scanning of technical signals on hourly/15m intervals.
- Notification: Send immediate email/alert when a high EV signal is detected.
- Integration: Triggered by GitHub Actions every hour.
"""

import logging
from datetime import datetime
from analysis.tech_swing_analyzer import TechnicalSwingAnalyzer
from auto_trading.email_reporter import EmailReporter
from config import RECIPIENT_EMAIL

class IntradayMonitor:
    def __init__(self):
        self.analyzer = TechnicalSwingAnalyzer()
        self.reporter = EmailReporter()
        self.logger = logging.getLogger("IntradayMonitor")
        logging.basicConfig(level=logging.INFO)

    def scan_and_alert(self, tickers: list[str], interval: str = "1h"):
        """인트라데이 신호 스캔 및 알림 발송"""
        self.logger.info(f"Starting intraday scan for {len(tickers)} tickers at {interval}...")
        
        # 1. 멀티 분석 수행 (1h)
        results = self.analyzer.run_multi_analysis(tickers, interval=interval, period="3mo")
        
        if not results:
            self.logger.info("No signals found in this scan.")
            return

        # 2. 고강도 신호만 필터링 (예: EV > 2% 또는 특정 패턴)
        high_priority_signals = []
        for res in results:
            for sig in res['signals']:
                if sig['ev_pct'] >= 1.5:  # 임계값 설정
                    high_priority_signals.append({
                        "ticker": res['ticker'],
                        "price": res['price'],
                        "signal": sig
                    })

        if not high_priority_signals:
            self.logger.info("No high-priority signals found.")
            return

        # 3. 긴급 이메일 알림 (Reporter 재사용)
        self.logger.info(f"Found {len(high_priority_signals)} HP signals! Sending alert...")
        self.send_alert_email(high_priority_signals, interval)

    def send_alert_email(self, signals: list[dict], interval: str):
        """긴급 신호 발생 시 이메일 발송"""
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        subject = f"🚨 [긴급/인트라데이] {len(signals)}개 종목 기술적 타점 발생 ({interval})"
        
        html = f"""
        <html>
        <body style='font-family: sans-serif;'>
            <h2 style='color:#e74c3c;'>🚨 인트라데이 기술적 매수 신호 포착</h2>
            <p>분석 시각: {now_str} (주기: {interval})</p>
            <table border='1' style='border-collapse: collapse; width: 100%;'>
                <tr style='background: #f4f4f4;'>
                    <th>티커</th>
                    <th>현재가</th>
                    <th>전략</th>
                    <th>기대수익(EV)</th>
                    <th>TP / SL</th>
                </tr>
        """
        for s in signals:
            sig = s['signal']
            html += f"""
                <tr>
                    <td><b>{s['ticker']}</b></td>
                    <td>{s['price']:,.2f}</td>
                    <td>{sig['strategy']}<br/><small>{sig['reason']}</small></td>
                    <td style='color:green; font-weight:bold;'>{sig['ev_pct']:+.2f}%</td>
                    <td>▲{sig['tp_price']:,.2f} / ▼{sig['sl_price']:,.2f}</td>
                </tr>
            """
        
        html += """
            </table>
            <p style='color:#666; font-size:0.9em; margin-top:20px;'>
                * 본 알림은 24시간 실시간 감시 시스템(GitHub Actions)에 의해 생성되었습니다.
            </p>
        </body>
        </html>
        """
        
        # EmailReporter의 발송 기능 활용 (메시지만 변경)
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        import smtplib
        from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS

        msg = MIMEMultipart("alternative")
        msg['Subject'] = subject
        msg['From'] = SMTP_USER
        msg['To'] = RECIPIENT_EMAIL
        msg.attach(MIMEText(html, 'html', 'utf-8'))

        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, RECIPIENT_EMAIL, msg.as_string())
        
        self.logger.info("Alert email sent successfully.")

if __name__ == "__main__":
    monitor = IntradayMonitor()
    # 주요 감시 대상
    target_tickers = ["TQQQ", "SOXX", "NVDA", "TSLA", "BTC-USD", "ETH-USD"]
    monitor.scan_and_alert(target_tickers, interval="1h")
