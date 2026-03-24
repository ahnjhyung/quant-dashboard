"""
state_machine.py
================
HFT 차익거래 엔진의 '뇌'. 모든 거래의 상태를 추적하고 안전한 전이만 허용함.
"""
from enum import Enum, auto
from typing import Optional, Dict, Any
import time

class ArbState(Enum):
    IDLE = auto()
    SCANNING = auto()
    SIGNAL_FOUND = auto()
    VALIDATING = auto()
    EXECUTING_LEG1 = auto()
    LEG1_FILLED = auto()
    EXECUTING_LEG2 = auto()
    LEG2_FILLED = auto()
    UNWINDING = auto()
    HALTED = auto()

class StateMachine:
    def __init__(self, initial_state: ArbState = ArbState.IDLE):
        self._current_state = initial_state
        self._last_update = time.time()
        self._context: Dict[str, Any] = {}

    @property
    def current_state(self) -> ArbState:
        return self._current_state

    def transition_to(self, new_state: ArbState, context_update: Optional[Dict[str, Any]] = None):
        """상태 전이 규칙 검사 후 상태 변경"""
        allowed = self._is_transition_allowed(self._current_state, new_state)
        
        if not allowed:
            print(f"[CRITICAL] Abnormal state transition attempt: {self._current_state.name} -> {new_state.name}")
            self._current_state = ArbState.HALTED
            return

        self._current_state = new_state
        self._last_update = time.time()
        if context_update:
            self._context.update(context_update)
        
        print(f"[STATE] {new_state.name} | Context: {len(self._context)} items")

    def _is_transition_allowed(self, current: ArbState, next_s: ArbState) -> bool:
        """상태 전이 화이트리스트 루틴"""
        if current == ArbState.HALTED: return False

        rules = {
            ArbState.IDLE: [ArbState.SCANNING, ArbState.HALTED],
            ArbState.SCANNING: [ArbState.SIGNAL_FOUND, ArbState.IDLE, ArbState.HALTED],
            ArbState.SIGNAL_FOUND: [ArbState.VALIDATING, ArbState.IDLE, ArbState.HALTED],
            ArbState.VALIDATING: [ArbState.EXECUTING_LEG1, ArbState.IDLE, ArbState.HALTED],
            ArbState.EXECUTING_LEG1: [ArbState.LEG1_FILLED, ArbState.UNWINDING, ArbState.HALTED],
            ArbState.LEG1_FILLED: [ArbState.EXECUTING_LEG2, ArbState.HALTED],
            ArbState.EXECUTING_LEG2: [ArbState.LEG2_FILLED, ArbState.UNWINDING, ArbState.HALTED],
            ArbState.LEG2_FILLED: [ArbState.IDLE, ArbState.HALTED],
            ArbState.UNWINDING: [ArbState.IDLE, ArbState.HALTED],
        }
        return next_s in rules.get(current, [])

    def get_context(self) -> Dict[str, Any]: return self._context
    def clear_context(self): self._context = {}
