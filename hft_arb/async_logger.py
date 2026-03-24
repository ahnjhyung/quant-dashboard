"""
async_logger.py — 비동기 Supabase 기록 모듈
============================================
[설계 원칙]
  - 매매 체결 이후 'fire-and-forget' 방식으로 비동기 실행
  - EV 계산 및 체결 경로에서 완전히 분리 (지연 없음)
  - DB 오류 발생 시 로컬 파일 백업 (fallback)

[SecurityAuditor MEDIUM]
  - 로그에 포지션 크기/금액은 마스킹 처리
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# [SecurityAuditor CRITICAL] config.py 경유로만 로드
try:
    from config import SUPABASE_URL, SUPABASE_KEY
except ImportError:
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
    logger.warning("[AsyncLogger] config.py 없음 — 환경변수에서 로드")

FALLBACK_LOG_PATH = Path(__file__).parent / "logs" / "arb_signals.jsonl"


class AsyncLogger:
    """
    비동기 Supabase 신호 기록기.

    체결 후 asyncio.create_task()로 호출되어 메인 루프를 블로킹하지 않는다.

    Args:
        table_name: Supabase 테이블명
        flush_interval: 배치 flush 간격 (초)
    """

    def __init__(self, table_name: str = "arb_signals", flush_interval: float = 2.0):
        self.table_name = table_name
        self.flush_interval = flush_interval
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False

        # 로컬 fallback 디렉토리 생성
        FALLBACK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    async def log(self, data: dict) -> None:
        """비동기 큐에 기록 요청 (비블로킹)."""
        # [SecurityAuditor MEDIUM] 금액 마스킹
        safe_data = {k: ("***" if k in ("position_size", "ev_usd") else v) for k, v in data.items()}
        logger.debug(f"[AsyncLogger] 신호 큐 추가: {safe_data}")
        await self._queue.put(data)

    async def run(self) -> None:
        """배치 flush 루프 (데몬에서 task로 실행)."""
        self._running = True
        while self._running:
            await asyncio.sleep(self.flush_interval)
            await self._flush()

    async def _flush(self) -> None:
        """큐에 쌓인 신호를 Supabase에 배치 삽입."""
        batch = []
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                item["recorded_at"] = time.time()
                batch.append(item)
            except asyncio.QueueEmpty:
                break

        if not batch:
            return

        if not SUPABASE_URL or not SUPABASE_KEY:
            # Supabase 미설정 시 로컬 파일 백업
            self._write_fallback(batch)
            return

        try:
            headers = {
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            }
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{SUPABASE_URL}/rest/v1/{self.table_name}",
                    headers=headers,
                    json=batch,
                )
                if resp.status_code not in (200, 201):
                    logger.warning(f"[AsyncLogger] Supabase 응답 오류: {resp.status_code}")
                    self._write_fallback(batch)
        except Exception as e:
            logger.error(f"[AsyncLogger] Supabase 기록 실패: {e}")
            self._write_fallback(batch)

    def _write_fallback(self, batch: list[dict]) -> None:
        """로컬 JSONL 파일 백업."""
        try:
            with FALLBACK_LOG_PATH.open("a", encoding="utf-8") as f:
                for item in batch:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"[AsyncLogger] 로컬 백업 실패: {e}")

    def stop(self) -> None:
        self._running = False
