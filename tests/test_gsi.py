"""
Unit tests for Valve CS2 Game State Integration (GSI) Models, HTTP Server, and Installer.
"""

import json
import urllib.request
from pathlib import Path
import pytest
from PySide6.QtCore import QCoreApplication

from kronos_veil.gsi.installer import (
    CFG_FILENAME,
    generate_cfg_content,
    install_cfg,
    uninstall_cfg,
    verify_cfg_installed,
)
from kronos_veil.gsi.models import GameState, MapState, PlayerState, RoundState
from kronos_veil.gsi.server import GsiServer


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


SAMPLE_GSI_PAYLOAD = {
    "provider": {
        "name": "Counter-Strike: Global Offensive",
        "appid": 730,
        "version": 14000,
        "steamid": "76561198000000000",
        "timestamp": 1690000000,
    },
    "map": {
        "mode": "competitive",
        "name": "de_inferno",
        "phase": "live",
        "round": 4,
        "team_ct": {"score": 2},
        "team_t": {"score": 1},
    },
    "round": {
        "phase": "live",
        "win_team": "CT",
        "bomb": "planted",
    },
    "player": {
        "steamid": "76561198000000000",
        "name": "Shroud",
        "team": "CT",
        "activity": "playing",
        "state": {
            "health": 85,
            "armor": 100,
            "helmet": True,
            "flashed": 0,
            "burning": 0,
            "money": 3400,
            "round_kills": 2,
            "round_killhs": 1,
            "equip_value": 4750,
        },
        "match_stats": {
            "kills": 12,
            "assists": 3,
            "deaths": 2,
            "mvps": 2,
            "score": 28,
        },
    },
    "auth": {
        "token": "secret_token_123",
    },
}


def test_game_state_parsing_full():
    state = GameState.from_json(SAMPLE_GSI_PAYLOAD)

    assert state.provider_name == "Counter-Strike: Global Offensive"
    assert state.provider_appid == 730
    assert state.auth_token == "secret_token_123"

    # Map assertions
    assert state.map.name == "de_inferno"
    assert state.map.mode == "competitive"
    assert state.map.round == 4
    assert state.map.team_ct_score == 2
    assert state.map.team_t_score == 1

    # Round assertions
    assert state.round.phase == "live"
    assert state.round.is_live is True
    assert state.round.is_bomb_planted is True
    assert state.round.win_team == "CT"

    # Player assertions
    assert state.player.name == "Shroud"
    assert state.player.team == "CT"
    assert state.player.activity == "playing"
    assert state.player.health == 85
    assert state.player.armor == 100
    assert state.player.helmet is True
    assert state.player.kills == 12
    assert state.player.round_kills == 2

    # Convenience properties
    assert state.is_in_game is True
    assert state.is_player_alive is True
    assert state.is_round_live is True
    assert state.is_bomb_planted is True


def test_game_state_parsing_empty_and_corrupt():
    state = GameState.from_json({})
    assert state.is_in_game is False
    assert state.is_player_alive is False
    assert state.round.is_live is False
    assert state.round.is_bomb_planted is False

    # Test non-dict
    state_none = GameState.from_json(None)  # type: ignore
    assert state_none.is_in_game is False


def test_installer_generate_cfg():
    cfg = generate_cfg_content(port=31337, auth_token="my_token")
    assert '"uri" "http://127.0.0.1:31337"' in cfg
    assert '"token" "my_token"' in cfg
    assert '"player_state"        "1"' in cfg

    # Without token
    cfg_no_token = generate_cfg_content(port=27015)
    assert '"uri" "http://127.0.0.1:27015"' in cfg_no_token
    assert '"auth"' not in cfg_no_token


def test_installer_file_lifecycle(tmp_path: Path):
    target_dir = tmp_path / "csgo" / "cfg"
    assert verify_cfg_installed(target_dir) is False

    success, msg = install_cfg(target_dir=target_dir, port=31337)
    assert success is True
    assert (target_dir / CFG_FILENAME).exists()
    assert verify_cfg_installed(target_dir) is True

    # Check content
    content = (target_dir / CFG_FILENAME).read_text(encoding="utf-8")
    assert "KronosVeil" in content

    # Test uninstall
    del_ok, del_msg = uninstall_cfg(target_dir=target_dir)
    assert del_ok is True
    assert not (target_dir / CFG_FILENAME).exists()
    assert verify_cfg_installed(target_dir) is False


def test_gsi_server_http_and_signals(qapp):
    port = 31399
    server = GsiServer(host="127.0.0.1", port=port, auth_token="gsi_test_auth")
    started = server.start()
    assert started is True
    assert server.is_running is True

    received_states = []
    received_phases = []
    received_bombs = []

    server.bridge.state_updated.connect(received_states.append)
    server.bridge.round_phase_changed.connect(received_phases.append)
    server.bridge.bomb_state_changed.connect(received_bombs.append)

    try:
        # 1. Test GET healthcheck
        req = urllib.request.Request(f"http://127.0.0.1:{port}/")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "running"
            assert data["service"] == "Kronos Veil GSI Server"

        # 2. Test POST with incorrect auth token -> 401
        unauth_payload = json.dumps({"auth": {"token": "wrong"}}).encode("utf-8")
        post_req_unauth = urllib.request.Request(
            f"http://127.0.0.1:{port}/",
            data=unauth_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(post_req_unauth, timeout=2.0)
        assert exc_info.value.code == 401

        # 3. Test POST with valid payload -> 200
        valid_payload = dict(SAMPLE_GSI_PAYLOAD)
        valid_payload["auth"] = {"token": "gsi_test_auth"}
        encoded_data = json.dumps(valid_payload).encode("utf-8")

        post_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/",
            data=encoded_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(post_req, timeout=2.0) as resp:
            assert resp.status == 200
            res = json.loads(resp.read().decode("utf-8"))
            assert res["status"] == "ok"

        # Process Qt events
        qapp.processEvents()

        assert len(received_states) >= 1
        assert received_states[-1].player.name == "Shroud"
        assert len(received_phases) >= 1
        assert received_phases[-1] == "live"
        assert len(received_bombs) >= 1
        assert received_bombs[-1] == "planted"

    finally:
        server.stop()
        assert server.is_running is False
