"""
Unit tests for Smart Q&A Extraction Engine in Kronos Veil v1.3.

Covers:
- QuestionItem dataclass serialization and factory methods
- QuestionExtractor heuristics across multiple languages (EN, ES, FR, DE, TR)
- False-positive suppression (bot commands, short queries, emote noise, copypastas, spam)
- Duplicate question suppression
- QuestionDeckManager lifecycle, capacity limits, auto-expiration, and state transitions
"""

import time
import pytest
from PySide6.QtCore import QCoreApplication

from kronos_veil.chat.base import ChatMessage
from kronos_veil.chat.questions import (
    QuestionDeckManager,
    QuestionExtractor,
    QuestionItem,
)


@pytest.fixture(autouse=True)
def qapp():
    """Ensure a QCoreApplication instance exists for PySide6 signals."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


# ============================================================================
# 1. QuestionItem Dataclass Tests
# ============================================================================


def test_question_item_defaults():
    item = QuestionItem(author="TestUser", text="What is your sens?")
    assert item.id is not None
    assert len(item.id) > 10
    assert item.author == "TestUser"
    assert item.text == "What is your sens?"
    assert item.platform == "demo"
    assert item.badges == []
    assert item.is_answered is False
    assert item.is_dismissed is False
    assert item.created_at > 0
    assert item.timestamp is not None


def test_question_item_from_chat_message():
    msg = ChatMessage(
        username="ProGamer",
        message="  Why did you buy the AWP?  ",
        platform="twitch",
        badges=["subscriber", "vip"],
    )
    item = QuestionItem.from_chat_message(msg)

    assert item.author == "ProGamer"
    assert item.text == "Why did you buy the AWP?"
    assert item.platform == "twitch"
    assert item.badges == ["subscriber", "vip"]
    assert item.is_answered is False
    assert item.is_dismissed is False


def test_question_item_to_dict():
    item = QuestionItem(
        id="q-1234",
        author="Viewer99",
        text="How to improve crosshair placement?",
        platform="youtube",
        badges=["moderator"],
        created_at=1700000000.0,
        is_answered=True,
        is_dismissed=False,
    )
    d = item.to_dict()

    assert d["id"] == "q-1234"
    assert d["author"] == "Viewer99"
    assert d["text"] == "How to improve crosshair placement?"
    assert d["platform"] == "youtube"
    assert d["badges"] == ["moderator"]
    assert d["created_at"] == 1700000000.0
    assert d["is_answered"] is True
    assert d["is_dismissed"] is False


# ============================================================================
# 2. QuestionExtractor: Heuristic Question Detection Tests
# ============================================================================


def test_extractor_english_questions_with_question_mark():
    extractor = QuestionExtractor()

    assert extractor.is_question("What sensitivity do you play on?") is True
    assert extractor.is_question("Why did you peek that angle?") is True
    assert extractor.is_question("How do you control the AK recoil?") is True
    assert extractor.is_question("When does the next match start?") is True
    assert extractor.is_question("Where did you buy that mousepad?") is True
    assert extractor.is_question("Who is your favorite CS player?") is True
    assert extractor.is_question("Which crosshair code are you using?") is True
    assert extractor.is_question("Can you play Brimstone next game?") is True
    assert extractor.is_question("Do you prefer stretched resolution?") is True
    assert extractor.is_question("Is this your primary streaming PC?") is True


def test_extractor_english_interrogative_structures_without_question_mark():
    extractor = QuestionExtractor()

    # Viewer omitting the question mark but clearly asking a question
    assert extractor.is_question("what sensitivity do you play on") is True
    assert extractor.is_question("how to rank up fast in cs2") is True
    assert extractor.is_question("why did you choose this agent") is True
    assert extractor.is_question("can you show your graphics settings") is True
    assert extractor.is_question("could you teach us that smoke lineup") is True
    assert extractor.is_question("would you play with viewers later") is True
    assert extractor.is_question("does anyone know the tournament bracket") is True


def test_extractor_leading_mentions_and_greetings():
    extractor = QuestionExtractor()

    # Greetings and streamer mentions stripped before question analysis
    assert extractor.is_question("Hey @Shroud what sensitivity do you use?") is True
    assert extractor.is_question("bro can you show your crosshair code") is True
    assert extractor.is_question("yo streamer why did you rotate so late") is True
    assert extractor.is_question("@Streamer how do you practice aim") is True


def test_extractor_non_question_statements():
    extractor = QuestionExtractor()

    assert extractor.is_question("That was an amazing clutch bro") is False
    assert extractor.is_question("I really love watching your streams") is False
    assert extractor.is_question("GG WP everyone in the chat") is False
    assert extractor.is_question("Nice try, unlucky round") is False
    assert extractor.is_question("I don't know why he did that") is False
    assert extractor.is_question("This is how we win this match") is False
    assert extractor.is_question("") is False
    assert extractor.is_question("   ") is False


# ============================================================================
# 3. QuestionExtractor: Multi-Language Detection Tests
# ============================================================================


def test_extractor_spanish_questions():
    extractor = QuestionExtractor()

    # Spanish with inverted question marks and accents
    assert extractor.is_question("¿Cómo configuras tu mira?") is True
    assert extractor.is_question("¿Qué resolución usas para jugar?") is True
    assert extractor.is_question("Por qué juegas con esa arma?") is True
    assert extractor.is_question("Por qué no compraste chaleco") is True
    assert extractor.is_question("Cuándo harás stream con seguidores") is True
    assert extractor.is_question("Dónde compraste ese teclado") is True
    assert extractor.is_question("Puedes mostrar tu configuración") is True


def test_extractor_french_questions():
    extractor = QuestionExtractor()

    # French question words and structures
    assert extractor.is_question("Pourquoi tu as fait ce choix?") is True
    assert extractor.is_question("Comment tu t'entraînes pour le tournoi?") is True
    assert extractor.is_question("Est-ce que tu vas stream demain?") is True
    assert extractor.is_question("Où trouver ton crosshair") is True
    assert extractor.is_question("Quand commence la prochaine partie") is True
    assert extractor.is_question("Peux-tu montrer tes paramètres graphiques") is True


def test_extractor_german_questions():
    extractor = QuestionExtractor()

    # German question words and structures
    assert extractor.is_question("Warum spielst du diese Map?") is True
    assert extractor.is_question("Wie lange spielst du schon CS?") is True
    assert extractor.is_question("Wann fängt das nächste Spiel an") is True
    assert extractor.is_question("Kannst du die Settings zeigen") is True
    assert extractor.is_question("Wo hast du das gelernt") is True
    assert extractor.is_question("Warum hast du die AWP gedroppt") is True


def test_extractor_turkish_questions():
    extractor = QuestionExtractor()

    # Turkish question words and question suffixes (mı/mi/misin)
    assert extractor.is_question("Bu oyunu kaç saat oynadın?") is True
    assert extractor.is_question("Rankın ne zaman sıfırlanıyor?") is True
    assert extractor.is_question("Nasıl bu kadar iyi vuruyorsun") is True
    assert extractor.is_question("Neden bu silahı seçtin") is True
    assert extractor.is_question("Crosshair kodunu paylaşır mısın") is True
    assert extractor.is_question("Yarın akşam yayın açacak mısın") is True
    assert extractor.is_question("Bu ayarları nereden buldun") is True
    assert extractor.is_question("Yeni güncellemeyi beğendin mi") is True


# ============================================================================
# 4. QuestionExtractor: False-Positive Suppression Tests
# ============================================================================


def test_extractor_suppress_bot_commands():
    extractor = QuestionExtractor()

    assert extractor.is_question("!sens") is False
    assert extractor.is_question("!rank?") is False
    assert extractor.is_question("/me is asking a question?") is False
    assert extractor.is_question(".points?") is False
    assert extractor.is_question("$gamble 500?") is False
    assert extractor.is_question("%drops?") is False
    assert extractor.is_question("~uptime?") is False


def test_extractor_suppress_short_noise_and_queries():
    extractor = QuestionExtractor()

    # Punctuation only
    assert extractor.is_question("?") is False
    assert extractor.is_question("???") is False
    assert extractor.is_question("? ! ?") is False

    # 1-word reaction queries
    assert extractor.is_question("what?") is False
    assert extractor.is_question("why?") is False
    assert extractor.is_question("how?") is False
    assert extractor.is_question("who?") is False
    assert extractor.is_question("huh?") is False
    assert extractor.is_question("quoi?") is False
    assert extractor.is_question("was?") is False
    assert extractor.is_question("ne?") is False
    assert extractor.is_question("qué?") is False

    # Trivial 2-word reactions
    assert extractor.is_question("who is?") is False
    assert extractor.is_question("why not?") is False
    assert extractor.is_question("what now?") is False
    assert extractor.is_question("how come?") is False


def test_extractor_suppress_emote_noise():
    extractor = QuestionExtractor()

    assert extractor.is_question("KEKW ???") is False
    assert extractor.is_question("OMEGALUL ?") is False
    assert extractor.is_question("Pog ???") is False
    assert extractor.is_question("LUL what?") is False
    assert extractor.is_question("what? KEKW") is False
    assert extractor.is_question("monkaS ???") is False
    assert extractor.is_question("catJAM ???") is False
    assert extractor.is_question("PepeHands why?") is False


def test_extractor_allow_emotes_with_real_questions():
    extractor = QuestionExtractor()

    # Emotes embedded in genuine substantive questions
    assert extractor.is_question("KEKW why did you rush B alone?") is True
    assert extractor.is_question("What mouse do you use Pog?") is True
    assert extractor.is_question("OMEGALUL how did you survive that round?") is True
    assert extractor.is_question("Can you play Jett next game catJAM?") is True


def test_extractor_suppress_copypastas_and_spam():
    extractor = QuestionExtractor()

    # Repetitive word spam / copypasta
    assert extractor.is_question("why why why why why why why?") is False
    assert extractor.is_question("can you win? can you win? can you win? can you win?") is False

    # Extreme punctuation / character spam
    assert extractor.is_question("??????????????????????????????") is False
    assert extractor.is_question("whaaaaaaaaaaaaaaaaaat???????") is False

    # Exclamations that start with interrogative words
    assert extractor.is_question("What a clutch!") is False
    assert extractor.is_question("What an awesome round!") is False


def test_extractor_duplicate_spam_window():
    extractor = QuestionExtractor(duplicate_window_sec=1.5)

    # First attempt passes
    assert extractor.is_duplicate_spam("SpamViewer", "What is your sensitivity?") is False

    # Immediate repetition by the same author is suppressed as duplicate
    assert extractor.is_duplicate_spam("SpamViewer", "What is your sensitivity?") is True
    assert extractor.is_duplicate_spam("SpamViewer", "what is your sensitivity?") is True

    # Different author asking after a brief pause is permitted
    assert extractor.is_duplicate_spam("OtherViewer", "What is your mouse DPI?") is False

    # Rapid global repetition of the exact same query within 4s is suppressed
    assert extractor.is_duplicate_spam("ThirdViewer", "What is your mouse DPI?") is True

    # After duplicate window expires, original author can ask again
    time.sleep(1.6)
    assert extractor.is_duplicate_spam("SpamViewer", "What is your sensitivity?") is False


def test_extractor_extract_chat_message():
    extractor = QuestionExtractor()

    # Real question message
    msg1 = ChatMessage(username="Alice", message="What is your favorite map?")
    item1 = extractor.extract(msg1)
    assert item1 is not None
    assert item1.author == "Alice"
    assert item1.text == "What is your favorite map?"

    # Non-question message
    msg2 = ChatMessage(username="Bob", message="Good job on that round!")
    assert extractor.extract(msg2) is None

    # System message
    msg3 = ChatMessage(username="System", message="What is your sensitivity?", is_system=True)
    assert extractor.extract(msg3) is None


# ============================================================================
# 5. QuestionDeckManager Tests (Capacity, Expiration, State Transitions)
# ============================================================================


def test_deck_manager_signals_and_addition():
    manager = QuestionDeckManager(qa_max_items=10)

    added_items = []
    manager.question_added.connect(added_items.append)

    item = QuestionItem(author="Viewer1", text="What is your keyboard?")
    assert manager.add_question(item) is True

    assert len(added_items) == 1
    assert added_items[0].id == item.id
    assert manager.count() == 1
    assert manager.active_count() == 1


def test_deck_manager_capacity_limits():
    manager = QuestionDeckManager(qa_max_items=3)

    removed_ids = []
    manager.question_removed.connect(removed_ids.append)

    t0 = time.time()
    q1 = QuestionItem(id="q1", author="u1", text="Question 1", created_at=t0 + 1.0)
    q2 = QuestionItem(id="q2", author="u2", text="Question 2", created_at=t0 + 2.0)
    q3 = QuestionItem(id="q3", author="u3", text="Question 3", created_at=t0 + 3.0)

    manager.add_question(q1)
    manager.add_question(q2)
    manager.add_question(q3)
    assert manager.count() == 3

    # Adding a 4th question evicts the oldest (q1)
    q4 = QuestionItem(id="q4", author="u4", text="Question 4", created_at=t0 + 4.0)
    manager.add_question(q4)

    assert manager.count() == 3
    assert len(removed_ids) == 1
    assert removed_ids[0] == "q1"
    assert manager.get_question("q1") is None
    assert manager.get_question("q4") is not None


def test_deck_manager_eviction_prioritizes_answered_or_dismissed():
    manager = QuestionDeckManager(qa_max_items=3)

    removed_ids = []
    manager.question_removed.connect(removed_ids.append)

    t0 = time.time()
    q1 = QuestionItem(id="q1", author="u1", text="Question 1", created_at=t0 + 1.0)
    q2 = QuestionItem(id="q2", author="u2", text="Question 2", created_at=t0 + 2.0)
    q3 = QuestionItem(id="q3", author="u3", text="Question 3", created_at=t0 + 3.0)

    manager.add_question(q1)
    manager.add_question(q2)
    manager.add_question(q3)

    # Mark q2 as answered
    manager.mark_answered("q2")

    # Add 4th question: q2 should be evicted first even though q1 is older,
    # because q2 is already answered!
    q4 = QuestionItem(id="q4", author="u4", text="Question 4", created_at=t0 + 4.0)
    manager.add_question(q4)

    assert manager.count() == 3
    assert removed_ids == ["q2"]
    assert manager.get_question("q1") is not None
    assert manager.get_question("q2") is None


def test_deck_manager_auto_expiration():
    manager = QuestionDeckManager(qa_max_items=10, qa_auto_expire_seconds=60)

    removed_ids = []
    manager.question_removed.connect(removed_ids.append)

    t0 = time.time()
    q1 = QuestionItem(id="q1", author="u1", text="Question 1", created_at=t0)
    q2 = QuestionItem(id="q2", author="u2", text="Question 2", created_at=t0 + 30.0)

    manager.add_question(q1)
    manager.add_question(q2)

    # At t0 + 45: neither is expired (ages: 45s and 15s <= 60s)
    expired = manager.cleanup_expired(now=t0 + 45.0)
    assert expired == []
    assert manager.count() == 2

    # At t0 + 65: q1 is expired (age 65s > 60s), q2 is not (age 35s <= 60s)
    expired = manager.cleanup_expired(now=t0 + 65.0)
    assert expired == ["q1"]
    assert removed_ids == ["q1"]
    assert manager.count() == 1
    assert manager.get_question("q1") is None
    assert manager.get_question("q2") is not None


def test_deck_manager_zero_auto_expire_never_expires():
    manager = QuestionDeckManager(qa_max_items=10, qa_auto_expire_seconds=0)

    q = QuestionItem(id="q1", created_at=100.0)
    manager.add_question(q)

    # Even far in the future, it should never expire
    assert manager.cleanup_expired(now=999999.0) == []
    assert manager.count() == 1


def test_deck_manager_state_transitions():
    manager = QuestionDeckManager()

    updated_items = []
    manager.question_updated.connect(updated_items.append)

    q1 = QuestionItem(id="q1", text="Question 1")
    q2 = QuestionItem(id="q2", text="Question 2")
    manager.add_question(q1)
    manager.add_question(q2)

    # Mark q1 answered
    assert manager.mark_answered("q1") is True
    assert q1.is_answered is True
    assert len(updated_items) == 1
    assert updated_items[-1].id == "q1"

    # Dismiss q2
    assert manager.dismiss_question("q2") is True
    assert q2.is_dismissed is True
    assert len(updated_items) == 2
    assert updated_items[-1].id == "q2"

    # Active questions should exclude both answered and dismissed by default
    active = manager.get_active_questions()
    assert len(active) == 0

    # Including answered
    with_answered = manager.get_active_questions(include_answered=True)
    assert len(with_answered) == 1
    assert with_answered[0].id == "q1"

    # Including dismissed
    with_dismissed = manager.get_active_questions(include_dismissed=True)
    assert len(with_dismissed) == 1
    assert with_dismissed[0].id == "q2"


def test_deck_manager_process_message_pipeline():
    manager = QuestionDeckManager(qa_max_items=5)

    # Valid question
    msg_valid = ChatMessage(username="ViewerX", message="What sensitivity do you recommend for CS2?")
    item = manager.process_message(msg_valid)
    assert item is not None
    assert manager.count() == 1
    assert item.author == "ViewerX"

    # Bot command
    msg_bot = ChatMessage(username="ViewerY", message="!sens")
    assert manager.process_message(msg_bot) is None
    assert manager.count() == 1

    # Emote noise
    msg_noise = ChatMessage(username="ViewerZ", message="KEKW ???")
    assert manager.process_message(msg_noise) is None
    assert manager.count() == 1


def test_deck_manager_clear_and_remove():
    manager = QuestionDeckManager()

    cleared = []
    removed = []
    manager.deck_cleared.connect(lambda: cleared.append(True))
    manager.question_removed.connect(removed.append)

    manager.add_question(QuestionItem(id="q1", text="Question 1"))
    manager.add_question(QuestionItem(id="q2", text="Question 2"))
    assert manager.count() == 2

    # Remove single question
    assert manager.remove_question("q1") is True
    assert manager.count() == 1
    assert removed == ["q1"]

    # Clear entire deck
    manager.clear()
    assert manager.count() == 0
    assert len(cleared) == 1
