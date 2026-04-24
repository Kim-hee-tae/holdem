"""Simple Texas Hold'em engine and CLI demo.

Run:
    python holdem.py
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import random
from collections import Counter

RANK_ORDER = "23456789TJQKA"
RANK_TO_VALUE = {r: i + 2 for i, r in enumerate(RANK_ORDER)}
VALUE_TO_RANK = {v: r for r, v in RANK_TO_VALUE.items()}
SUITS = ("S", "H", "D", "C")
HAND_NAMES = {
    8: "Straight Flush",
    7: "Four of a Kind",
    6: "Full House",
    5: "Flush",
    4: "Straight",
    3: "Three of a Kind",
    2: "Two Pair",
    1: "One Pair",
    0: "High Card",
}


@dataclass(frozen=True, order=True)
class Card:
    rank: str
    suit: str

    @property
    def value(self) -> int:
        return RANK_TO_VALUE[self.rank]

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"


class Deck:
    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.cards = [Card(rank, suit) for suit in SUITS for rank in RANK_ORDER]

    def shuffle(self) -> None:
        self._rng.shuffle(self.cards)

    def deal(self, n: int) -> list[Card]:
        if n > len(self.cards):
            raise ValueError("Not enough cards in deck")
        dealt, self.cards = self.cards[:n], self.cards[n:]
        return dealt


def _straight_high(values: list[int]) -> int | None:
    uniq = sorted(set(values), reverse=True)
    if 14 in uniq:
        uniq.append(1)
    run = 1
    best = None
    for i in range(1, len(uniq)):
        if uniq[i - 1] - 1 == uniq[i]:
            run += 1
            if run >= 5:
                best = uniq[i - 4]
        else:
            run = 1
    return best


def evaluate_five(cards: list[Card]) -> tuple[int, tuple[int, ...]]:
    values = sorted((c.value for c in cards), reverse=True)
    counts = Counter(values)
    groups = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
    is_flush = len({c.suit for c in cards}) == 1
    straight_high = _straight_high(values)

    if is_flush and straight_high is not None:
        return (8, (straight_high,))

    if groups[0][1] == 4:
        quad = groups[0][0]
        kicker = max(v for v in values if v != quad)
        return (7, (quad, kicker))

    if groups[0][1] == 3 and groups[1][1] == 2:
        return (6, (groups[0][0], groups[1][0]))

    if is_flush:
        return (5, tuple(values))

    if straight_high is not None:
        return (4, (straight_high,))

    if groups[0][1] == 3:
        trips = groups[0][0]
        kickers = sorted((v for v in values if v != trips), reverse=True)
        return (3, (trips, *kickers))

    if groups[0][1] == 2 and groups[1][1] == 2:
        hi_pair = max(groups[0][0], groups[1][0])
        lo_pair = min(groups[0][0], groups[1][0])
        kicker = max(v for v in values if v != hi_pair and v != lo_pair)
        return (2, (hi_pair, lo_pair, kicker))

    if groups[0][1] == 2:
        pair = groups[0][0]
        kickers = sorted((v for v in values if v != pair), reverse=True)
        return (1, (pair, *kickers))

    return (0, tuple(values))


def best_hand(seven_cards: list[Card]) -> tuple[tuple[int, tuple[int, ...]], list[Card]]:
    if len(seven_cards) != 7:
        raise ValueError("Texas Hold'em hand evaluation requires exactly 7 cards")

    best_score = None
    best_combo = None
    for combo in combinations(seven_cards, 5):
        score = evaluate_five(list(combo))
        if best_score is None or score > best_score:
            best_score = score
            best_combo = list(combo)

    assert best_score is not None and best_combo is not None
    return best_score, best_combo


def format_cards(cards: list[Card]) -> str:
    return " ".join(str(c) for c in cards)


def describe_score(score: tuple[int, tuple[int, ...]]) -> str:
    category = HAND_NAMES[score[0]]
    return category


def play_demo(num_bots: int = 1, seed: int | None = None) -> None:
    if not (1 <= num_bots <= 8):
        raise ValueError("num_bots must be between 1 and 8")

    players = ["You"] + [f"Bot{i}" for i in range(1, num_bots + 1)]
    deck = Deck(seed=seed)
    deck.shuffle()

    hole_cards = {p: deck.deal(2) for p in players}
    _ = deck.deal(1)  # burn
    flop = deck.deal(3)
    _ = deck.deal(1)  # burn
    turn = deck.deal(1)
    _ = deck.deal(1)  # burn
    river = deck.deal(1)
    board = flop + turn + river

    print("=== Texas Hold'em Demo ===")
    print(f"Your cards: {format_cards(hole_cards['You'])}")
    print(f"Board: {format_cards(board)}")

    results = {}
    for p in players:
        score, combo = best_hand(hole_cards[p] + board)
        results[p] = (score, combo)

    top = max(results.values(), key=lambda x: x[0])[0]
    winners = [p for p, (score, _) in results.items() if score == top]

    print("\n--- Showdown ---")
    for p in players:
        score, combo = results[p]
        print(
            f"{p:>5}: {format_cards(hole_cards[p])} -> {describe_score(score)} "
            f"({format_cards(combo)})"
        )

    print("\nWinner(s):", ", ".join(winners), f"with {describe_score(top)}")


if __name__ == "__main__":
    play_demo(num_bots=3)
