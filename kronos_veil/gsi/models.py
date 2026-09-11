"""
Valve CS2 Game State Integration (GSI) Data Models.
Provides structured, type-safe representations of player, round, and map telemetry.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class PlayerState:
    """Represents local client or spectated player state."""

    steamid: str = ""
    name: str = ""
    team: str = ""  # "CT", "T", or ""
    activity: str = "menu"  # "playing", "menu", "textinput"
    health: int = 100
    armor: int = 0
    helmet: bool = False
    flashed: int = 0  # 0 to 255
    burning: int = 0  # 0 to 255
    money: int = 0
    round_kills: int = 0
    round_killhs: int = 0
    equip_value: int = 0
    kills: int = 0
    assists: int = 0
    deaths: int = 0
    mvps: int = 0
    score: int = 0

    @property
    def is_alive(self) -> bool:
        """Returns True if player is active in a match and has health > 0."""
        return self.health > 0 and self.activity == "playing"


@dataclass
class RoundState:
    """Represents current match round phase and bomb status."""

    phase: str = ""  # "freezetime", "live", "over"
    win_team: Optional[str] = None  # "CT", "T"
    bomb: Optional[str] = None  # "planted", "exploded", "defused"

    @property
    def is_live(self) -> bool:
        return self.phase.lower() == "live"

    @property
    def is_freezetime(self) -> bool:
        return self.phase.lower() == "freezetime"

    @property
    def is_over(self) -> bool:
        return self.phase.lower() == "over"

    @property
    def is_bomb_planted(self) -> bool:
        return (self.bomb or "").lower() == "planted"

    @property
    def is_bomb_defused(self) -> bool:
        return (self.bomb or "").lower() == "defused"

    @property
    def is_bomb_exploded(self) -> bool:
        return (self.bomb or "").lower() == "exploded"


@dataclass
class MapState:
    """Represents active map mode, name, and team scores."""

    mode: str = ""
    name: str = ""
    phase: str = ""  # "warmup", "intermission", "gameover", "live"
    round: int = 0
    team_ct_score: int = 0
    team_t_score: int = 0

    @property
    def is_warmup(self) -> bool:
        return self.phase.lower() == "warmup"

    @property
    def is_gameover(self) -> bool:
        return self.phase.lower() == "gameover"


@dataclass
class GameState:
    """Complete snapshot of CS2 Game State Integration payload."""

    provider_name: str = ""
    provider_appid: int = 730
    provider_version: int = 0
    provider_timestamp: int = 0
    player: PlayerState = field(default_factory=PlayerState)
    round: RoundState = field(default_factory=RoundState)
    map: MapState = field(default_factory=MapState)
    auth_token: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def is_in_game(self) -> bool:
        """True if player is currently connected to a map and playing."""
        return bool(self.map.name and self.player.activity == "playing")

    @property
    def is_player_alive(self) -> bool:
        return self.player.is_alive

    @property
    def is_round_live(self) -> bool:
        return self.round.is_live

    @property
    def is_bomb_planted(self) -> bool:
        return self.round.is_bomb_planted

    @classmethod
    def from_json(cls, payload: Dict[str, Any]) -> GameState:
        """Parses a Valve GSI JSON payload dictionary into a structured GameState."""
        if not isinstance(payload, dict):
            return cls()

        provider_data = payload.get("provider", {})
        player_data = payload.get("player", {})
        player_state_data = player_data.get("state", {}) if isinstance(player_data, dict) else {}
        player_match_stats = player_data.get("match_stats", {}) if isinstance(player_data, dict) else {}
        round_data = payload.get("round", {})
        map_data = payload.get("map", {})
        auth_data = payload.get("auth", {})

        # Parse player
        player = PlayerState(
            steamid=str(player_data.get("steamid", "") or ""),
            name=str(player_data.get("name", "") or ""),
            team=str(player_data.get("team", "") or ""),
            activity=str(player_data.get("activity", "menu") or "menu"),
            health=int(player_state_data.get("health", 100) if isinstance(player_state_data, dict) else 100),
            armor=int(player_state_data.get("armor", 0) if isinstance(player_state_data, dict) else 0),
            helmet=bool(player_state_data.get("helmet", False) if isinstance(player_state_data, dict) else False),
            flashed=int(player_state_data.get("flashed", 0) if isinstance(player_state_data, dict) else 0),
            burning=int(player_state_data.get("burning", 0) if isinstance(player_state_data, dict) else 0),
            money=int(player_state_data.get("money", 0) if isinstance(player_state_data, dict) else 0),
            round_kills=int(player_state_data.get("round_kills", 0) if isinstance(player_state_data, dict) else 0),
            round_killhs=int(player_state_data.get("round_killhs", 0) if isinstance(player_state_data, dict) else 0),
            equip_value=int(player_state_data.get("equip_value", 0) if isinstance(player_state_data, dict) else 0),
            kills=int(player_match_stats.get("kills", 0) if isinstance(player_match_stats, dict) else 0),
            assists=int(player_match_stats.get("assists", 0) if isinstance(player_match_stats, dict) else 0),
            deaths=int(player_match_stats.get("deaths", 0) if isinstance(player_match_stats, dict) else 0),
            mvps=int(player_match_stats.get("mvps", 0) if isinstance(player_match_stats, dict) else 0),
            score=int(player_match_stats.get("score", 0) if isinstance(player_match_stats, dict) else 0),
        )

        # Parse round
        round_state = RoundState(
            phase=str(round_data.get("phase", "") or "") if isinstance(round_data, dict) else "",
            win_team=round_data.get("win_team") if isinstance(round_data, dict) else None,
            bomb=round_data.get("bomb") if isinstance(round_data, dict) else None,
        )

        # Parse map
        team_ct_data = map_data.get("team_ct", {}) if isinstance(map_data, dict) else {}
        team_t_data = map_data.get("team_t", {}) if isinstance(map_data, dict) else {}
        ct_score = team_ct_data.get("score", 0) if isinstance(team_ct_data, dict) else 0
        t_score = team_t_data.get("score", 0) if isinstance(team_t_data, dict) else 0

        map_state = MapState(
            mode=str(map_data.get("mode", "") or "") if isinstance(map_data, dict) else "",
            name=str(map_data.get("name", "") or "") if isinstance(map_data, dict) else "",
            phase=str(map_data.get("phase", "") or "") if isinstance(map_data, dict) else "",
            round=int(map_data.get("round", 0) if isinstance(map_data, dict) else 0),
            team_ct_score=int(ct_score or 0),
            team_t_score=int(t_score or 0),
        )

        # Auth token
        token = str(auth_data.get("token", "") or "") if isinstance(auth_data, dict) else ""

        return cls(
            provider_name=str(provider_data.get("name", "") or "") if isinstance(provider_data, dict) else "",
            provider_appid=int(provider_data.get("appid", 730) if isinstance(provider_data, dict) else 730),
            provider_version=int(provider_data.get("version", 0) if isinstance(provider_data, dict) else 0),
            provider_timestamp=int(provider_data.get("timestamp", 0) if isinstance(provider_data, dict) else 0),
            player=player,
            round=round_state,
            map=map_state,
            auth_token=token,
            raw_data=payload,
            timestamp=time.time(),
        )
