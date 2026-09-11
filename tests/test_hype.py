"""
Unit tests for Hype Spike & OBS Auto-Clip Engine (HypeDetector).
Tests sliding window math, emote intensity weighting, spike detection thresholds,
rate-limiting cooldown protection, and OBS auto-clip invocation.
"""

from unittest.mock import MagicMock
import pytest
from PySide6.QtCore import QCoreApplication

from kronos_veil.chat.base import ChatMessage
from kronos_veil.chat.demo import DemoChatProvider
from kronos_veil.chat.hype import HypeDetector, HypeSpikeEvent
from kronos_veil.config import AppSettings
from kronos_veil.obs.client import OBSWebSocketClient


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def test_hype_detector_initialization(qapp):
    settings = AppSettings(
        hype_detector_enabled=True,
        hype_window_seconds=15,
        hype_threshold_rate=3.5,
        hype_auto_clip=False,
        hype_cooldown_seconds=60,
    )
    detector = HypeDetector(settings=settings)

    assert detector.threshold == 3.5
    assert detector.window_seconds == 15
    assert detector.cooldown_seconds == 60
    assert detector.current_velocity == 0.0
    assert detector.cooldown_remaining == 0.0
    assert detector.is_on_cooldown is False
    assert detector.obs_client is None


def test_sliding_window_math_basic_messages(qapp):
    settings = AppSettings(hype_window_seconds=10, hype_threshold_rate=5.0)
    detector = HypeDetector(settings=settings)

    velocities = []
    detector.velocity_updated.connect(velocities.append)

    # Ingest 5 basic messages (score 1.0 each) at t=0
    for i in range(5):
        vel = detector.process_message(f"message {i}", timestamp=0.0)
    assert vel == pytest.approx(0.5)  # 5.0 score / 10s = 0.5 msgs/s
    assert detector.current_velocity == pytest.approx(0.5)
    assert len(velocities) == 5

    # At t=5, add 5 more basic messages
    for i in range(5):
        vel = detector.process_message(f"message {i}", timestamp=5.0)
    assert vel == pytest.approx(1.0)  # 10.0 score / 10s = 1.0 msgs/s

    # At t=11, messages from t=0.0 (< 11.0 - 10.0 = 1.0) must be evicted
    # Window should now contain only the 5 messages from t=5.0
    vel_at_11 = detector.get_velocity(now=11.0)
    assert vel_at_11 == pytest.approx(0.5)  # 5.0 score / 10s = 0.5 msgs/s

    # At t=16, all messages (t=0 and t=5) must be evicted
    vel_at_16 = detector.get_velocity(now=16.0)
    assert vel_at_16 == 0.0


def test_emote_weighting_and_intensity(qapp):
    settings = AppSettings(hype_window_seconds=10)
    detector = HypeDetector(settings=settings)

    # 1. Message without emotes: base score = 1.0
    vel = detector.process_message("hello everyone", timestamp=10.0)
    assert vel == pytest.approx(0.1)  # 1.0 / 10s

    # 2. Message with KEKW (weight 2.0) -> score = 1.0 + 2.0 = 3.0
    # Total score = 1.0 + 3.0 = 4.0
    vel = detector.process_message("that was funny KEKW", timestamp=10.0)
    assert vel == pytest.approx(0.4)  # 4.0 / 10s

    # 3. Message with lowercase emote and punctuation "pogchamp!"
    # Weight 2.0 -> score = 1.0 + 2.0 = 3.0
    # Total score = 4.0 + 3.0 = 7.0
    vel = detector.process_message("omg pogchamp!", timestamp=10.0)
    assert vel == pytest.approx(0.7)

    # 4. Message with multiple reaction emotes: "EZ Clap OMEGALUL"
    # EZ (1.2) + Clap (1.2) + OMEGALUL (2.5) = 4.9 emote score + 1.0 base = 5.9
    # Total score = 7.0 + 5.9 = 12.9
    vel = detector.process_message("EZ Clap OMEGALUL", timestamp=10.0)
    assert vel == pytest.approx(1.29)

    # 5. Custom registered emote
    detector.register_emote("SUPERHYPE", weight=5.0)
    vel = detector.process_message("let's go SUPERHYPE", timestamp=10.0)
    # 12.9 + (1.0 base + 5.0 emote) = 18.9 -> 18.9 / 10 = 1.89
    assert vel == pytest.approx(1.89)


def test_spike_threshold_detection(qapp):
    settings = AppSettings(
        hype_window_seconds=10,
        hype_threshold_rate=3.0,
        hype_cooldown_seconds=60,
    )
    detector = HypeDetector(settings=settings)

    detected_spikes = []
    detector.hype_spike_detected.connect(detected_spikes.append)

    # Message burst below threshold (score = 20.0, velocity = 2.0 < 3.0)
    for _ in range(4):
        detector.process_message("Pog Pog", timestamp=100.0)  # 1.0 + 2*2.0 = 5.0 each -> total 20.0
    assert len(detected_spikes) == 0
    assert detector.current_velocity == pytest.approx(2.0)

    # Cross threshold with 3 more hype messages -> total score = 35.0, velocity = 3.5 >= 3.0
    for _ in range(3):
        detector.process_message("Pog Pog", timestamp=101.0)

    assert len(detected_spikes) == 1
    spike: HypeSpikeEvent = detected_spikes[0]
    assert spike.velocity >= 3.0
    assert spike.threshold == 3.0
    # Spike triggered exactly on the 6th message (6 * 5.0 = 30.0 -> vel 3.0)
    assert spike.message_count == 6
    assert spike.emote_count == 12
    assert "Pog" in spike.top_emotes
    assert spike.timestamp == 101.0
    assert not spike.auto_clipped
    assert not spike.clip_triggered


def test_cooldown_protection(qapp):
    settings = AppSettings(
        hype_window_seconds=10,
        hype_threshold_rate=3.0,
        hype_cooldown_seconds=45,
    )
    detector = HypeDetector(settings=settings)

    detected_spikes = []
    detector.hype_spike_detected.connect(detected_spikes.append)

    # Trigger initial spike at t=100.0
    for _ in range(10):
        detector.process_message("KEKW PogChamp", timestamp=100.0)  # 1.0 + 2.0 + 2.0 = 5.0 each -> 50.0 / 10 = 5.0

    assert len(detected_spikes) == 1
    assert detector.is_on_cooldown is True
    assert detector.cooldown_remaining == pytest.approx(45.0)

    # At t=120.0 (20 seconds later, 25 seconds of cooldown remaining)
    # A massive burst occurs: must NOT trigger a new spike
    for _ in range(10):
        detector.process_message("KEKW KEKW KEKW KEKW", timestamp=120.0)

    assert len(detected_spikes) == 1
    assert detector.is_on_cooldown is True
    assert detector.cooldown_remaining == pytest.approx(25.0)

    # At t=145.0, cooldown exactly expires (145.0 - 100.0 = 45.0s)
    assert detector.get_cooldown_remaining(now=145.0) == 0.0

    # At t=146.0, cooldown is clear -> next burst triggers a new spike!
    for _ in range(10):
        detector.process_message("OMEGALUL OMEGALUL", timestamp=146.0)

    assert len(detected_spikes) == 2
    assert detector.cooldown_remaining == pytest.approx(45.0)


def test_obs_auto_clip_enabled(qapp):
    settings = AppSettings(
        hype_window_seconds=10,
        hype_threshold_rate=2.5,
        hype_auto_clip=True,
    )
    mock_obs = MagicMock(spec=OBSWebSocketClient)
    detector = HypeDetector(settings=settings, obs_client=mock_obs)

    spikes = []
    detector.hype_spike_detected.connect(spikes.append)

    # Cross threshold
    for _ in range(6):
        detector.process_message("KEKW Pog", timestamp=50.0)

    assert len(spikes) == 1
    assert spikes[0].auto_clipped is True
    assert spikes[0].clip_triggered is True

    # Verify OBS methods invoked
    mock_obs.create_stream_marker.assert_called_once()
    marker_arg = mock_obs.create_stream_marker.call_args[0][0]
    assert "Hype Spike" in marker_arg
    mock_obs.save_replay_buffer.assert_called_once()


def test_obs_auto_clip_disabled(qapp):
    settings = AppSettings(
        hype_window_seconds=10,
        hype_threshold_rate=2.5,
        hype_auto_clip=False,  # disabled
    )
    mock_obs = MagicMock(spec=OBSWebSocketClient)
    detector = HypeDetector(settings=settings, obs_client=mock_obs)

    spikes = []
    detector.hype_spike_detected.connect(spikes.append)

    for _ in range(6):
        detector.process_message("KEKW Pog", timestamp=50.0)

    assert len(spikes) == 1
    assert spikes[0].auto_clipped is False
    mock_obs.create_stream_marker.assert_not_called()
    mock_obs.save_replay_buffer.assert_not_called()


def test_simulate_spike(qapp):
    settings = AppSettings(
        hype_threshold_rate=3.5,
        hype_auto_clip=True,
    )
    mock_obs = MagicMock(spec=OBSWebSocketClient)
    detector = HypeDetector(settings=settings)
    detector.attach_obs_client(mock_obs)

    spikes = []
    detector.hype_spike_detected.connect(spikes.append)

    # Simulate spike with custom velocity
    event = detector.simulate_spike(velocity=7.5)
    assert event is not None
    assert event.velocity == 7.5
    assert event.threshold == 3.5
    assert event.auto_clipped is True
    assert detector.current_velocity == pytest.approx(7.5)
    assert detector.is_on_cooldown is True

    assert len(spikes) == 1
    mock_obs.create_stream_marker.assert_called_once()
    mock_obs.save_replay_buffer.assert_called_once()


def test_reset(qapp):
    settings = AppSettings(hype_window_seconds=10, hype_threshold_rate=2.0)
    detector = HypeDetector(settings=settings)

    # Ingest 8 messages (8 * 3.0 = 24.0 score -> velocity 2.4 >= 2.0) to trigger spike
    for _ in range(8):
        detector.process_message("KEKW", timestamp=10.0)
    assert detector.current_velocity > 0.0
    assert detector.is_on_cooldown is True

    # Reset
    detector.reset()
    assert detector.current_velocity == 0.0
    assert detector.cooldown_remaining == 0.0
    assert detector.is_on_cooldown is False


def test_ignore_system_and_empty_messages(qapp):
    detector = HypeDetector()

    # System message must be ignored
    sys_msg = ChatMessage(message="Welcome streamer!", is_system=True)
    vel1 = detector.process_message(sys_msg)
    assert vel1 == 0.0
    assert detector.current_velocity == 0.0

    # Empty string must be ignored
    vel2 = detector.process_message("   ")
    assert vel2 == 0.0
    assert detector.current_velocity == 0.0


def test_disabled_detector(qapp):
    settings = AppSettings(hype_detector_enabled=False)
    detector = HypeDetector(settings=settings)

    spikes = []
    detector.hype_spike_detected.connect(spikes.append)

    vel = detector.process_message("KEKW KEKW KEKW KEKW KEKW")
    assert vel == 0.0
    assert len(spikes) == 0


def test_attach_chat_provider(qapp):
    detector = HypeDetector()
    provider = DemoChatProvider()
    detector.attach_chat_provider(provider)

    velocities = []
    detector.velocity_updated.connect(velocities.append)

    # Trigger provider message
    test_msg = ChatMessage(username="Tester", message="Let's go PogChamp!")
    provider.message_received.emit(test_msg)

    assert len(velocities) == 1
    assert velocities[0] > 0.0
