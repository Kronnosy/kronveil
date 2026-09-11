"""
Smart Q&A Extraction Engine for Kronos Veil.

Provides heuristic question extraction from livestream chat streams:
- Multi-language question detection (English, Spanish, French, German, Turkish)
- Rejection of bot commands, emote reactions, short queries, copypastas, and duplicate spam
- QuestionDeckManager with capacity limits, auto-expiration, and state lifecycle management
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QObject, Signal

from kronos_veil.chat.base import ChatMessage
from kronos_veil.chat.emotes import POPULAR_EMOTES

logger = logging.getLogger("KronosVeil.QA")

# Bot command prefixes to immediately suppress
COMMAND_PREFIXES: Tuple[str, ...] = ("!", "/", ".", "$", "%", "~", "^", "\\")

# Common chat emotes (7TV, Twitch, BTTV, FFZ, Kick)
KNOWN_EMOTES: Set[str] = {
    # Popular emotes from emotes.py
    *(k.lower() for k in POPULAR_EMOTES.keys()),
    # Common chat emotes & slang
    "poggers", "pepega", "5head", "nodders", "nopers", "pepejam",
    "gachihyper", "widepeeposad", "monkahmm", "pausechamp",
    "lulw", "jebaited", "trihard", "4head", "cmonbruh", "feelsbadman",
    "feelsgoodman", "smoge", "despair", "huuu", "aware", "clueless",
    "batchest", "surely", "bedge", "kekwait", "pepelaugh", "copium",
    "gigachad", "w", "l", "gg", "ggwp", "nt", "glhf",
}

# Trivial 1-2 word query tokens that represent reactions rather than substantive questions
TRIVIAL_WORDS: Set[str] = {
    # English
    "what", "why", "how", "who", "when", "where", "which", "whose", "whom",
    "is", "are", "it", "this", "that", "now", "not", "come", "do", "you",
    "he", "she", "they", "we", "was", "were", "did", "can", "so", "oh",
    "ah", "bro", "dude", "man", "really", "huh", "wait", "ok", "okay",
    # Spanish
    "que", "qué", "como", "cómo", "por", "cuando", "cuándo", "donde", "dónde",
    "quien", "quién", "cual", "cuál", "si", "no", "es",
    # French
    "quoi", "pourquoi", "comment", "quand", "qui", "est", "ce", "que",
    # German
    "was", "warum", "wie", "wann", "wer", "wo", "ist", "das", "nicht",
    # Turkish
    "ne", "neden", "nasıl", "nasil", "niye", "kim", "kaç", "kac", "mi", "mı", "mu", "mü",
}

# Interrogative starter patterns for sentence beginnings (or after greeting/mention)
INTERROGATIVE_STARTERS_REGEX = re.compile(
    r"^(?:"
    # English question words & auxiliary openers
    r"(?:what|why|how|when|where|who|whom|whose|which|"
    r"can you|could you|would you|should i|should we|will you|"
    r"do you|does anyone|did you|is it|is there|are you|have you|"
    r"has anyone|anybody know|anyone know)\b|"
    # Spanish question words & openers (also inverted ¿)
    r"(?:¿|qu[eé]|c[oó]mo|por qu[eé]|cu[aá]ndo|d[oó]nde|qui[eé]n|qui[eé]nes|cu[aá]l|cu[aá]les|"
    r"puedes|podr[ií]as|sabes si|alguien sabe)\b|"
    # French question words & openers
    r"(?:pourquoi|comment|quand|o[uù]|qui|quel|quelle|quels|quelles|"
    r"est-ce que|qu'est-ce que|peux-tu|pouvez-vous|sais-tu|savez-vous)\b|"
    # German question words & openers
    r"(?:warum|wie|wann|wo|wer|was|weshalb|wieso|wohin|woher|"
    r"kannst du|k[oö]nnen sie|wei[sß]t du|gibt es)\b|"
    # Turkish question words
    r"(?:nas[ıi]l|neden|ni[çc]in|niye|ne zaman|nerede|nereden|nereye|kim|hangi|ka[çc])\b"
    r")",
    re.IGNORECASE,
)

# Turkish question suffixes & clitics that can appear mid-sentence or end of sentence
TURKISH_QUESTION_SUFFIX_REGEX = re.compile(
    r"\b(?:m[ıiuü]|m[ıiuü]s[ıiuü]n|m[ıiuü]y[ıiuü]z|m[ıiuü]yd[ıiuü]|m[ıiuü]ym[ıiuü][sş]|m[ıiuü] acaba)\b",
    re.IGNORECASE,
)

# Turkish question words anywhere in clause
TURKISH_QUESTION_WORDS_REGEX = re.compile(
    r"\b(?:nas[ıi]l|neden|ni[çc]in|niye|ne zaman|nerede|nereden|nereye|hangi|ka[çc])\b",
    re.IGNORECASE,
)


@dataclass
class QuestionItem:
    """Represents an extracted question queued in the Smart Q&A Deck."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    author: str = ""
    text: str = ""
    timestamp: str = field(default_factory=lambda: time.strftime("%H:%M:%S"))
    created_at: float = field(default_factory=time.time)
    platform: str = "demo"
    badges: List[str] = field(default_factory=list)
    is_answered: bool = False
    is_dismissed: bool = False

    @classmethod
    def from_chat_message(cls, msg: ChatMessage) -> QuestionItem:
        """Create a QuestionItem from a standard ChatMessage."""
        return cls(
            author=msg.username,
            text=msg.message.strip(),
            timestamp=msg.timestamp,
            created_at=time.time(),
            platform=msg.platform,
            badges=list(msg.badges),
        )

    def to_dict(self) -> dict:
        """Serialize question item into a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "author": self.author,
            "text": self.text,
            "timestamp": self.timestamp,
            "created_at": self.created_at,
            "platform": self.platform,
            "badges": list(self.badges),
            "is_answered": self.is_answered,
            "is_dismissed": self.is_dismissed,
        }


class QuestionExtractor:
    """Heuristic extractor detecting real viewer questions while suppressing noise."""

    def __init__(
        self,
        duplicate_window_sec: float = 30.0,
        min_substantive_words: int = 2,
        min_alphanumeric_chars: int = 8,
    ) -> None:
        self.duplicate_window_sec = float(duplicate_window_sec)
        self.min_substantive_words = min_substantive_words
        self.min_alphanumeric_chars = min_alphanumeric_chars
        # Stores (timestamp, author_lower, text_norm)
        self._history: Deque[Tuple[float, str, str]] = deque()
        self._lock = threading.RLock()

    @staticmethod
    def _strip_mentions_and_greetings(text: str) -> str:
        """Strip leading mentions (@user) and vocatives (hey, hi, bro, streamer) before testing."""
        s = text.strip()
        pattern = re.compile(r"^(?:@\w+|hey|hi|yo|bro|dude|streamer)[\s,:]*", re.IGNORECASE)
        while True:
            m = pattern.match(s)
            if not m or not m.group():
                break
            s = s[m.end():].strip()
        return s

    def is_question(self, text: str) -> bool:
        """Evaluate whether text represents a genuine viewer question."""
        if not text:
            return False

        stripped = text.strip()
        if not stripped:
            return False

        # 1. Reject bot commands (!, /, ., $, etc.)
        if stripped.startswith(COMMAND_PREFIXES):
            return False

        # 2. Reject excessive punctuation ratio (> 50% punctuation)
        punct_chars = re.findall(r"[?!.,~@#$%^&*()_+=\-\[\]{}|\\:;\"<>/¿؟\uFF1F]", stripped)
        if len(punct_chars) / len(stripped) > 0.50:
            return False

        # 3. Reject extreme repeated character sequences (e.g., "????????" or "whaaaaaaaat")
        if re.search(r"(.)\1{7,}", stripped):
            return False

        # 4. Tokenize and remove emote words to assess substantive content
        raw_words = stripped.split()
        clean_words: List[str] = []
        for w in raw_words:
            # Strip outer punctuation
            cw = re.sub(r"^[^\w¿]+|[^\w?¿]+$", "", w).strip()
            if cw:
                clean_words.append(cw)

        # Substantive words: words not in known emotes
        substantive_words = [
            w for w in clean_words
            if w.lower() not in KNOWN_EMOTES and re.search(r"\w", w)
        ]

        # If zero substantive words (e.g. "KEKW ???", "???"), reject as noise/emote spam
        if len(substantive_words) < self.min_substantive_words:
            return False

        # Check total alphanumeric content
        substantive_text = "".join(substantive_words)
        alpha_chars = re.findall(r"\w", substantive_text)
        if len(alpha_chars) < self.min_alphanumeric_chars:
            return False

        # If exactly 2 words, reject if both words are trivial fillers/interrogatives (e.g., "what now?", "who is?")
        if len(substantive_words) == 2:
            w0 = re.sub(r"[^\w]", "", substantive_words[0].lower())
            w1 = re.sub(r"[^\w]", "", substantive_words[1].lower())
            if w0 in TRIVIAL_WORDS and w1 in TRIVIAL_WORDS:
                return False

        # 5. Check vocabulary diversity (suppress repetitive copypastas)
        lower_words = [re.sub(r"[^\w]", "", w.lower()) for w in substantive_words if re.sub(r"[^\w]", "", w)]
        if len(lower_words) >= 4:
            unique_ratio = len(set(lower_words)) / len(lower_words)
            if unique_ratio <= 0.40:
                return False

        # 6. Check question marks vs sentence structure
        has_question_mark = bool(re.search(r"[\?¿؟\uFF1F]", stripped))

        if has_question_mark:
            return True

        # If no question mark:
        # Reject exclamations ("What a clutch!", "What an ace!")
        if stripped.endswith("!") or re.match(r"^(?:what\s+a|what\s+an)\b", stripped, re.IGNORECASE):
            return False

        # Check Turkish question suffixes/clitics (e.g. "oynar mısın", "yayın var mı")
        if TURKISH_QUESTION_SUFFIX_REGEX.search(stripped):
            return True

        # Check Turkish question words mid-sentence (e.g. "Bu ayarları nereden buldun")
        if TURKISH_QUESTION_WORDS_REGEX.search(stripped):
            return True

        # Check interrogative starter at beginning of sentence or after greeting
        normalized_clause = self._strip_mentions_and_greetings(stripped)
        # Also remove leading emotes from clause
        tokens = normalized_clause.split()
        while tokens and tokens[0].lower() in KNOWN_EMOTES:
            tokens.pop(0)
        cleaned_start = " ".join(tokens)

        if INTERROGATIVE_STARTERS_REGEX.search(cleaned_start):
            return True

        return False

    def is_duplicate_spam(self, author: str, text: str) -> bool:
        """Check if message is duplicate spam from the same author or rapid channel spam."""
        now = time.time()
        user_norm = author.lower().strip()
        # Normalize text: lowercase, alphanumeric and basic spacing
        text_norm = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower())).strip()

        if not text_norm:
            return False

        with self._lock:
            # Prune expired entries
            while self._history and (now - self._history[0][0]) > self.duplicate_window_sec:
                self._history.popleft()

            # Check if this exact text was asked recently
            for entry_time, u, m in self._history:
                # Same user asking again within duplicate window
                if u == user_norm and m == text_norm:
                    return True
                # Global rapid spam: exact same question within 4 seconds by anyone
                if m == text_norm and (now - entry_time) < 4.0:
                    return True

            # Record entry
            self._history.append((now, user_norm, text_norm))
            return False

    def extract(self, msg: ChatMessage) -> Optional[QuestionItem]:
        """Extract a QuestionItem from ChatMessage if it qualifies as a question."""
        if msg.is_system:
            return None

        if not self.is_question(msg.message):
            return None

        if self.is_duplicate_spam(msg.username, msg.message):
            logger.debug("Suppressed duplicate question spam from %s: %s", msg.username, msg.message)
            return False

        return QuestionItem.from_chat_message(msg)

    def extract_from_text(
        self,
        author: str,
        text: str,
        platform: str = "demo",
        badges: Optional[List[str]] = None,
    ) -> Optional[QuestionItem]:
        """Extract a QuestionItem from raw author and text strings."""
        if not self.is_question(text):
            return None

        if self.is_duplicate_spam(author, text):
            return None

        return QuestionItem(
            author=author,
            text=text.strip(),
            platform=platform,
            badges=badges or [],
        )


class QuestionDeckManager(QObject):
    """
    Manages active Q&A questions with capacity constraints, auto-expiration,
    and streamer lifecycle state transitions.
    """

    question_added = Signal(QuestionItem)
    question_updated = Signal(QuestionItem)
    question_removed = Signal(str)
    deck_cleared = Signal()

    def __init__(
        self,
        qa_max_items: int = 20,
        qa_auto_expire_seconds: int = 300,
        extractor: Optional[QuestionExtractor] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.qa_max_items: int = max(1, int(qa_max_items))
        self.qa_auto_expire_seconds: int = max(0, int(qa_auto_expire_seconds))
        self.extractor: QuestionExtractor = extractor or QuestionExtractor()
        self._questions: Dict[str, QuestionItem] = {}
        self._lock = threading.RLock()

    def set_max_items(self, max_items: int) -> None:
        """Update maximum capacity for active questions and evict if over limit."""
        with self._lock:
            self.qa_max_items = max(1, int(max_items))
            while len(self._questions) > self.qa_max_items:
                self._evict_one()

    def set_auto_expire_seconds(self, seconds: int) -> None:
        """Update auto-expiration time threshold and trigger cleanup."""
        with self._lock:
            self.qa_auto_expire_seconds = max(0, int(seconds))
            self.cleanup_expired()

    def _evict_one(self) -> Optional[str]:
        """Evict a single question to maintain capacity.

        Prefers answered or dismissed questions, then oldest by created_at.
        """
        if not self._questions:
            return None

        candidate_id: Optional[str] = None
        oldest_time = float("inf")

        # 1. Try to evict answered or dismissed first
        for q_id, q in self._questions.items():
            if (q.is_answered or q.is_dismissed) and q.created_at < oldest_time:
                oldest_time = q.created_at
                candidate_id = q_id

        # 2. Otherwise evict oldest active item
        if candidate_id is None:
            oldest_time = float("inf")
            for q_id, q in self._questions.items():
                if q.created_at < oldest_time:
                    oldest_time = q.created_at
                    candidate_id = q_id

        if candidate_id is not None:
            del self._questions[candidate_id]
            self.question_removed.emit(candidate_id)
            return candidate_id

        return None

    def add_question(self, item: QuestionItem, now: Optional[float] = None) -> bool:
        """Add a QuestionItem into the deck, enforcing capacity limits."""
        with self._lock:
            # If already present, treat as update
            if item.id in self._questions:
                self._questions[item.id] = item
                self.question_updated.emit(item)
                return True

            # Clean expired items first
            self.cleanup_expired(now=now)

            # Evict if at or over capacity
            while len(self._questions) >= self.qa_max_items:
                evicted = self._evict_one()
                if evicted is None:
                    break

            self._questions[item.id] = item
            self.question_added.emit(item)
            return True

    def process_message(self, msg: ChatMessage) -> Optional[QuestionItem]:
        """Evaluate incoming chat message, extract question, and add to deck."""
        item = self.extractor.extract(msg)
        if item is not None:
            self.add_question(item)
            return item
        return None

    def mark_answered(self, question_id: str) -> bool:
        """Mark a question as answered and notify listeners."""
        with self._lock:
            item = self._questions.get(question_id)
            if item is None:
                return False
            item.is_answered = True
            self.question_updated.emit(item)
            return True

    def dismiss_question(self, question_id: str) -> bool:
        """Mark a question as dismissed and notify listeners."""
        with self._lock:
            item = self._questions.get(question_id)
            if item is None:
                return False
            item.is_dismissed = True
            self.question_updated.emit(item)
            return True

    def remove_question(self, question_id: str) -> bool:
        """Manually remove a question from the deck."""
        with self._lock:
            if question_id in self._questions:
                del self._questions[question_id]
                self.question_removed.emit(question_id)
                return True
            return False

    def get_question(self, question_id: str) -> Optional[QuestionItem]:
        """Retrieve a specific question by ID."""
        with self._lock:
            return self._questions.get(question_id)

    def get_all_questions(self) -> List[QuestionItem]:
        """Retrieve all questions currently stored in the deck."""
        with self._lock:
            return list(self._questions.values())

    def get_active_questions(
        self,
        include_answered: bool = False,
        include_dismissed: bool = False,
    ) -> List[QuestionItem]:
        """Retrieve active questions filtered by state."""
        with self._lock:
            self.cleanup_expired()
            results: List[QuestionItem] = []
            for q in self._questions.values():
                if not include_answered and q.is_answered:
                    continue
                if not include_dismissed and q.is_dismissed:
                    continue
                results.append(q)
            return results

    def cleanup_expired(self, now: Optional[float] = None) -> List[str]:
        """Remove questions that have exceeded qa_auto_expire_seconds."""
        if self.qa_auto_expire_seconds <= 0:
            return []

        current_time = time.time() if now is None else float(now)
        removed_ids: List[str] = []

        with self._lock:
            to_remove = [
                q.id for q in self._questions.values()
                if (current_time - q.created_at) > self.qa_auto_expire_seconds
            ]
            for q_id in to_remove:
                del self._questions[q_id]
                removed_ids.append(q_id)
                self.question_removed.emit(q_id)

        return removed_ids

    def clear(self) -> None:
        """Clear all questions from the deck."""
        with self._lock:
            self._questions.clear()
            self.deck_cleared.emit()

    def clear_deck(self) -> None:
        """Alias for clear()."""
        self.clear()

    def count(self) -> int:
        """Total number of stored questions."""
        with self._lock:
            return len(self._questions)

    def active_count(self) -> int:
        """Number of currently active (unanswered and undismissed) questions."""
        return len(self.get_active_questions(include_answered=False, include_dismissed=False))
