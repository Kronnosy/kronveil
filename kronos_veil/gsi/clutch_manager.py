"""
Clutch Mode Manager for Kronos Veil.
Tracks real-time game telemetry from Valve CS2 GSI, detects high-stakes combat situations
(1vX, low HP, bomb planted), and triggers zero-distraction chat overlay dimming.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from PySide6.QtCore import QObject, Signal

from kronos_veil.config import AppSettings
from kronos_veil.gsi.models import GameState
from kronos_veil.gsi.server import GsiServer

logger = logging.getLogger("KronosVeil.ClutchManager")


class ClutchState(str, Enum):
    """Lifecycle states of the Clutch Mode state machine."""

    IDLE = "idle"  # Outside game or in main menu
    COMBAT = "combat"  # In match, player alive, regular gameplay
    CLUTCH = "clutch"  # High-stakes situation: overlay dimmed for silence/focus
    ROUND_OVER = "round_over"  # Round concluded, results displayed


class ClutchManager(QObject):
    """
    Manages clutch silence automation based on CS2 GSI events.
    Fades out chat overlay when high concentration is required and restores it when safe.
    """

    # Signals
    clutch_started = Signal(str)  # trigger reason: "low_health", "bomb_planted", etc.
    clutch_ended = Signal(str)  # disengage reason: "round_over", "player_death", "condition_cleared"
    opacity_target_changed = Signal(float)  # target overlay opacity (e.g., 0.0 -> dim, 0.95 -> restored)
    state_changed = Signal(str)  # ClutchState value
    bomb_state_changed = Signal(str)  # "planted", "defused", "exploded", ""

    def __init__(self, settings: Optional[AppSettings] = None) -> None:
        super().__init__()
        self.settings = settings or AppSettings()
        self.state = ClutchState.IDLE
        self.active_reason: str = ""
        self._last_bomb_state: Optional[str] = None
        self._current_opacity_target: float = self.settings.overlay_opacity

    @property
    def is_clutch_active(self) -> bool:
        """Returns True if the overlay is currently in dimmed clutch silence mode."""
        return self.state == ClutchState.CLUTCH

    def attach_gsi_server(self, server: GsiServer) -> None:
        """Subscribes to GSI server state updates."""
        server.bridge.state_updated.connect(self.on_game_state)

    def update_settings(self, settings: AppSettings) -> None:
        """Updates internal reference to user configuration."""
        self.settings = settings
        if not self.settings.clutch_mode_enabled and self.state == ClutchState.CLUTCH:
            self._disengage_clutch("disabled")

    def on_game_state(self, state: GameState) -> None:
        """Processes an incoming GameState payload and evaluates clutch triggers."""
        # 1. Feature disabled check
        if not self.settings.clutch_mode_enabled:
            if self.state == ClutchState.CLUTCH:
                self._disengage_clutch("disabled")
            elif self.state != ClutchState.IDLE:
                self._transition_state(ClutchState.IDLE)
            return

        # 2. In-game presence check
        if not state.is_in_game:
            if self.state == ClutchState.CLUTCH:
                self._disengage_clutch("left_game")
            if self.state != ClutchState.IDLE:
                self._transition_state(ClutchState.IDLE)
            return

        # 3. Track bomb status changes
        current_bomb = state.round.bomb or ""
        if current_bomb != (self._last_bomb_state or ""):
            self._last_bomb_state = current_bomb
            self.bomb_state_changed.emit(current_bomb)

        # 4. Round phase & player status evaluation
        round_phase = state.round.phase.lower()

        if round_phase == "over":
            if self.state == ClutchState.CLUTCH:
                self._disengage_clutch("round_over")
            self._transition_state(ClutchState.ROUND_OVER)
            return

        if round_phase == "freezetime":
            if self.state == ClutchState.CLUTCH:
                self._disengage_clutch("freezetime")
            self._transition_state(ClutchState.COMBAT)
            return

        # Round is live
        if not state.player.is_alive:
            # Player is dead or spectating
            if self.state == ClutchState.CLUTCH:
                self._disengage_clutch("player_death")
            self._transition_state(ClutchState.COMBAT)
            return

        # Player is ALIVE in a LIVE round
        clutch_trigger = self._evaluate_clutch_conditions(state)

        if clutch_trigger:
            if self.state != ClutchState.CLUTCH:
                self._engage_clutch(clutch_trigger)
        else:
            if self.state == ClutchState.CLUTCH:
                self._disengage_clutch("condition_cleared")
            elif self.state != ClutchState.COMBAT:
                self._transition_state(ClutchState.COMBAT)

    def _evaluate_clutch_conditions(self, state: GameState) -> Optional[str]:
        """Evaluates whether the current game state satisfies clutch triggers."""
        # Condition 1: Bomb is planted
        if state.round.is_bomb_planted:
            return "bomb_planted"

        # Condition 2: Low Health
        if 0 < state.player.health <= self.settings.clutch_health_threshold:
            return "low_health"

        return None

    def _engage_clutch(self, reason: str) -> None:
        """Transitions into active clutch state and dims overlay opacity."""
        self.state = ClutchState.CLUTCH
        self.active_reason = reason
        dim_opacity = float(self.settings.clutch_dim_opacity)
        self._current_opacity_target = dim_opacity

        logger.info("Clutch Mode engaged [Reason: %s] -> dimming opacity to %.2f", reason, dim_opacity)
        self.clutch_started.emit(reason)
        self.opacity_target_changed.emit(dim_opacity)
        self.state_changed.emit(self.state.value)

    def _disengage_clutch(self, reason: str) -> None:
        """Restores normal overlay opacity and transitions out of clutch."""
        prev_reason = self.active_reason
        self.active_reason = ""
        normal_opacity = float(self.settings.overlay_opacity)
        self._current_opacity_target = normal_opacity

        logger.info("Clutch Mode disengaged [Reason: %s, Prior: %s] -> restoring opacity to %.2f", reason, prev_reason, normal_opacity)
        self.clutch_ended.emit(reason)
        self.opacity_target_changed.emit(normal_opacity)

    def _transition_state(self, new_state: ClutchState) -> None:
        """Internal helper to transition state and emit notification."""
        if self.state != new_state:
            self.state = new_state
            self.state_changed.emit(new_state.value)

    def reset(self) -> None:
        """Resets the state machine to default IDLE state."""
        if self.state == ClutchState.CLUTCH:
            self._disengage_clutch("reset")
        self.state = ClutchState.IDLE
        self.active_reason = ""
        self._last_bomb_state = None
        self._current_opacity_target = self.settings.overlay_opacity
        self.state_changed.emit(self.state.value)
