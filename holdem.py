"""Texas Hold'em engine with betting rounds, blinds, cash/tournament modes, and a small GUI.

Examples:
    python holdem.py --mode tournament --players 4 --hands 10
    python holdem.py --gui
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
import random
from typing import Literal

RANK_ORDER = "23456789TJQKA"
RANK_TO_VALUE = {r: i + 2 for i, r in enumerate(RANK_ORDER)}
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

Action = Literal["fold", "check", "call", "raise"]


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
        self._dealt: set[tuple[str, str]] = set()

    def shuffle(self) -> None:
        self._rng.shuffle(self.cards)

    def deal(self, n: int) -> list[Card]:
        dealt, self.cards = self.cards[:n], self.cards[n:]
        for c in dealt:
            key = (c.rank, c.suit)
            if key in self._dealt:
                raise RuntimeError(f"Duplicate card dealt: {c}")
            self._dealt.add(key)
        return dealt


@dataclass
class Player:
    name: str
    chips: int
    hole_cards: list[Card] = field(default_factory=list)
    folded: bool = False
    all_in: bool = False
    current_bet: int = 0
    hand_contribution: int = 0

    def reset_for_hand(self) -> None:
        self.hole_cards = []
        self.folded = False
        self.all_in = False
        self.current_bet = 0
        self.hand_contribution = 0

    @property
    def active(self) -> bool:
        return not self.folded and (self.chips > 0 or self.all_in)


@dataclass
class GameConfig:
    small_blind: int = 5
    big_blind: int = 10
    starting_stack: int = 500
    mode: Literal["cash", "tournament"] = "cash"
    rebuy_stack: int = 500


class TexasHoldemGame:
    def __init__(
        self,
        player_names: list[str],
        config: GameConfig | None = None,
        seed: int | None = None,
        human_player: str | None = None,
    ) -> None:
        if len(player_names) < 2:
            raise ValueError("At least 2 players are required")
        self.config = config or GameConfig()
        self.players = [Player(name=n, chips=self.config.starting_stack) for n in player_names]
        self.dealer_idx = 0
        self.pot = 0
        self.board: list[Card] = []
        self.current_bet = 0
        self.deck = Deck(seed=seed)
        self.rng = random.Random(seed)
        self.hand_no = 0
        self.logs: list[str] = []
        self.human_player = human_player

    @staticmethod
    def format_cards(cards: list[Card]) -> str:
        return " ".join(str(c) for c in cards)

    def _log(self, msg: str) -> None:
        self.logs.append(msg)

    def living_players(self) -> list[Player]:
        return [p for p in self.players if p.chips > 0 or p.all_in]

    def rotate_dealer(self) -> None:
        self.dealer_idx = (self.dealer_idx + 1) % len(self.players)

    def _next_index(self, idx: int) -> int:
        return (idx + 1) % len(self.players)

    def _collect_bet(self, player: Player, amount: int) -> int:
        actual = min(amount, player.chips)
        player.chips -= actual
        player.current_bet += actual
        player.hand_contribution += actual
        self.pot += actual
        if player.chips == 0:
            player.all_in = True
        return actual

    def _reset_bets(self) -> None:
        for p in self.players:
            p.current_bet = 0
        self.current_bet = 0

    def start_hand(self) -> None:
        self.hand_no += 1
        self.logs = [f"=== Hand {self.hand_no} ==="]
        self.board = []
        self.pot = 0
        self.deck = Deck(seed=self.rng.randint(0, 10**9))
        self.deck.shuffle()
        for p in self.players:
            p.reset_for_hand()

        if self.config.mode == "cash":
            for p in self.players:
                if p.chips == 0:
                    p.chips = self.config.rebuy_stack
                    self._log(f"{p.name} rebuys to {p.chips} chips.")

        for _ in range(2):
            for p in self.players:
                if p.chips > 0:
                    p.hole_cards.extend(self.deck.deal(1))

        self._assert_unique_cards_or_raise()
        self._post_blinds()

    def _post_blinds(self) -> None:
        sb_idx = self._next_index(self.dealer_idx)
        bb_idx = self._next_index(sb_idx)
        sb = self.players[sb_idx]
        bb = self.players[bb_idx]
        sb_paid = self._collect_bet(sb, self.config.small_blind)
        bb_paid = self._collect_bet(bb, self.config.big_blind)
        self.current_bet = max(sb.current_bet, bb.current_bet)
        self._log(f"{sb.name} posts SB {sb_paid}.")
        self._log(f"{bb.name} posts BB {bb_paid}.")

    def _active_for_action(self) -> list[Player]:
        return [p for p in self.players if not p.folded and not p.all_in and p.chips >= 0]

    def _can_continue(self) -> bool:
        in_hand = [p for p in self.players if not p.folded and (p.chips > 0 or p.all_in)]
        return len(in_hand) > 1

    def decide_action(self, player: Player) -> tuple[Action, int]:
        to_call = max(0, self.current_bet - player.current_bet)
        if self.human_player is not None and player.name == self.human_player:
            return self._prompt_human_action(player, to_call)
        if to_call == 0:
            if player.chips > self.config.big_blind and self.rng.random() < 0.2:
                raise_to = self.current_bet + self.config.big_blind
                return "raise", raise_to
            return "check", 0

        if player.chips <= to_call:
            return "call", 0

        roll = self.rng.random()
        if roll < 0.15:
            return "fold", 0
        if roll < 0.75:
            return "call", 0
        raise_to = self.current_bet + self.config.big_blind
        return "raise", raise_to

    def _prompt_human_action(self, player: Player, to_call: int) -> tuple[Action, int]:
        prompt = (
            f"[{player.name}] chips={player.chips} to_call={to_call} "
            "action(fold/check/call/raise): "
        )
        while True:
            raw = input(prompt).strip().lower()
            if raw in {"fold", "f"}:
                return "fold", 0
            if raw in {"check", "k"} and to_call == 0:
                return "check", 0
            if raw in {"call", "c"}:
                return "call", 0
            if raw.startswith("raise") or raw.startswith("r"):
                parts = raw.split()
                if len(parts) == 2 and parts[1].isdigit():
                    return "raise", int(parts[1])
                return "raise", self.current_bet + self.config.big_blind
            print("Invalid action. Use fold/check/call/raise [amount].")

    def apply_action(self, player: Player, action: Action, raise_to: int = 0) -> None:
        to_call = max(0, self.current_bet - player.current_bet)
        if action == "fold":
            player.folded = True
            self._log(f"{player.name} folds.")
            return

        if action == "check":
            self._log(f"{player.name} checks.")
            return

        if action == "call":
            paid = self._collect_bet(player, to_call)
            self._log(f"{player.name} calls {paid}.")
            return

        if action == "raise":
            target = max(raise_to, self.current_bet + self.config.big_blind)
            need_total = max(0, target - player.current_bet)
            paid = self._collect_bet(player, need_total)
            if player.current_bet > self.current_bet:
                self.current_bet = player.current_bet
            self._log(f"{player.name} raises to {player.current_bet} (added {paid}).")
            return

        raise ValueError(f"Unknown action: {action}")

    def betting_round(self, start_idx: int) -> None:
        n = len(self.players)
        acted = 0
        idx = start_idx
        while acted < n * 2:
            if not self._can_continue():
                return

            p = self.players[idx]
            if not p.folded and not p.all_in:
                need = self.current_bet - p.current_bet
                everyone_matched = all(
                    x.folded or x.all_in or x.current_bet == self.current_bet
                    for x in self.players
                )
                if everyone_matched and need == 0 and acted >= n:
                    break
                action, raise_to = self.decide_action(p)
                self.apply_action(p, action, raise_to)
            idx = (idx + 1) % n
            acted += 1

        # If someone raised near the end, ensure everyone gets chance to match.
        unsettled = any(
            not x.folded and not x.all_in and x.current_bet != self.current_bet
            for x in self.players
        )
        if unsettled and self._can_continue():
            self.betting_round(idx)

    def deal_flop(self) -> None:
        _ = self.deck.deal(1)
        self.board.extend(self.deck.deal(3))
        self._assert_unique_cards_or_raise()
        self._log(f"Flop: {self.format_cards(self.board)}")

    def deal_turn(self) -> None:
        _ = self.deck.deal(1)
        self.board.extend(self.deck.deal(1))
        self._assert_unique_cards_or_raise()
        self._log(f"Turn: {self.format_cards(self.board)}")

    def deal_river(self) -> None:
        _ = self.deck.deal(1)
        self.board.extend(self.deck.deal(1))
        self._assert_unique_cards_or_raise()
        self._log(f"River: {self.format_cards(self.board)}")

    def _assert_unique_cards_or_raise(self) -> None:
        seen: set[tuple[str, str]] = set()
        all_cards = [c for p in self.players for c in p.hole_cards] + self.board
        for c in all_cards:
            key = (c.rank, c.suit)
            if key in seen:
                raise RuntimeError(f"Duplicate card detected in hand state: {c}")
            seen.add(key)

    def showdown_or_award(self) -> list[Player]:
        remain = [p for p in self.players if not p.folded]
        self._log("Hole cards reveal:")
        for p in self.players:
            self._log(f" - {p.name}: {self.format_cards(p.hole_cards)}")
        if len(remain) == 1:
            winner = remain[0]
            winner.chips += self.pot
            self._log(f"{winner.name} wins uncontested pot {self.pot}.")
            self.pot = 0
            return [winner]

        scored: list[tuple[Player, tuple[int, tuple[int, ...]]]] = []
        for p in remain:
            score, _ = best_hand(p.hole_cards + self.board)
            scored.append((p, score))
            self._log(f"{p.name}: {self.format_cards(p.hole_cards)} -> {HAND_NAMES[score[0]]}")

        side_pot_winners = self._distribute_side_pots(scored)
        return side_pot_winners

    def _distribute_side_pots(
        self, scored: list[tuple[Player, tuple[int, tuple[int, ...]]]]
    ) -> list[Player]:
        score_by_name = {p.name: score for p, score in scored}
        contributions = {p.name: p.hand_contribution for p in self.players}
        levels = sorted({amt for amt in contributions.values() if amt > 0})
        prev = 0
        all_winners: list[Player] = []
        total_distributed = 0

        for level in levels:
            eligible_for_pot = [p for p in self.players if contributions[p.name] >= level]
            pot_amount = (level - prev) * len(eligible_for_pot)
            prev = level
            if pot_amount <= 0:
                continue

            contenders = [p for p in eligible_for_pot if not p.folded and p.name in score_by_name]
            if not contenders:
                continue

            best = max(score_by_name[p.name] for p in contenders)
            winners = [p for p in contenders if score_by_name[p.name] == best]
            share, extra = divmod(pot_amount, len(winners))
            for i, w in enumerate(winners):
                w.chips += share + (1 if i < extra else 0)
                all_winners.append(w)
            total_distributed += pot_amount
            self._log(
                f"Side pot {pot_amount}: {', '.join(w.name for w in winners)} win."
            )

        self._log(f"Total pot distributed: {total_distributed}.")
        self.pot = 0
        dedup = []
        seen = set()
        for w in all_winners:
            if w.name not in seen:
                dedup.append(w)
                seen.add(w.name)
        return dedup

    def cleanup_tournament_players(self) -> None:
        if self.config.mode != "tournament":
            return
        # Keep seated players but mark elimination in log.
        for p in self.players:
            if p.chips == 0:
                self._log(f"{p.name} is eliminated.")

    def play_hand(self) -> list[Player]:
        self.start_hand()
        utg = self._next_index(self._next_index(self._next_index(self.dealer_idx)))
        self._log("-- Preflop betting --")
        self.betting_round(utg)
        if not self._can_continue():
            winners = self.showdown_or_award()
            self.rotate_dealer()
            self.cleanup_tournament_players()
            return winners

        self._reset_bets()
        self.deal_flop()
        self._log("-- Flop betting --")
        self.betting_round(self._next_index(self.dealer_idx))
        if not self._can_continue():
            winners = self.showdown_or_award()
            self.rotate_dealer()
            self.cleanup_tournament_players()
            return winners

        self._reset_bets()
        self.deal_turn()
        self._log("-- Turn betting --")
        self.betting_round(self._next_index(self.dealer_idx))
        if not self._can_continue():
            winners = self.showdown_or_award()
            self.rotate_dealer()
            self.cleanup_tournament_players()
            return winners

        self._reset_bets()
        self.deal_river()
        self._log("-- River betting --")
        self.betting_round(self._next_index(self.dealer_idx))
        winners = self.showdown_or_award()
        self.rotate_dealer()
        self.cleanup_tournament_players()
        return winners

    def session_finished(self) -> bool:
        if self.config.mode != "tournament":
            return False
        alive = [p for p in self.players if p.chips > 0]
        return len(alive) <= 1

    def standings(self) -> str:
        return " | ".join(f"{p.name}:{p.chips}" for p in self.players)


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


def simulate_session(
    mode: Literal["cash", "tournament"],
    players: int,
    hands: int,
    seed: int | None = None,
    interactive: bool = False,
) -> str:
    names = [f"P{i}" for i in range(1, players + 1)]
    config = GameConfig(mode=mode)
    human = names[0] if interactive else None
    game = TexasHoldemGame(names, config=config, seed=seed, human_player=human)
    session_logs = [f"Mode={mode}"]
    for _ in range(hands):
        game.play_hand()
        session_logs.extend(game.logs)
        session_logs.append(f"Standings: {game.standings()}")
        if game.session_finished():
            break
    if mode == "tournament":
        alive = [p.name for p in game.players if p.chips > 0]
        if len(alive) == 1:
            session_logs.append(f"Champion: {alive[0]}")
    return "\n".join(session_logs)


def launch_gui() -> None:
    import tkinter as tk
    from tkinter import ttk

    game = TexasHoldemGame(["You", "Bot1", "Bot2", "Bot3"], config=GameConfig(mode="cash"))

    root = tk.Tk()
    root.title("Texas Hold'em Demo")

    text = tk.Text(root, width=90, height=28)
    text.pack(padx=8, pady=8)

    def play_hand_ui() -> None:
        game.play_hand()
        text.delete("1.0", tk.END)
        text.insert(tk.END, "\n".join(game.logs) + "\n")
        text.insert(tk.END, f"\nStandings: {game.standings()}\n")

    btn_frame = ttk.Frame(root)
    btn_frame.pack(pady=6)
    ttk.Button(btn_frame, text="Play Next Hand", command=play_hand_ui).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="Quit", command=root.destroy).pack(side=tk.LEFT, padx=4)

    play_hand_ui()
    root.mainloop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Texas Hold'em simulation")
    parser.add_argument("--mode", choices=["cash", "tournament"], default="cash")
    parser.add_argument("--players", type=int, default=4)
    parser.add_argument("--hands", type=int, default=5)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--web", action="store_true")
    return parser.parse_args()


def launch_web_gui(seed: int | None = None) -> None:
    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "FastAPI web mode requires uvicorn and fastapi. Install with: pip install fastapi uvicorn"
        ) from exc

    from webapp.main import create_app

    app = create_app(seed=seed)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


def main() -> None:
    args = parse_args()
    if args.web:
        launch_web_gui(seed=args.seed)
        return
    if args.gui:
        launch_gui()
        return
    print(
        simulate_session(
            mode=args.mode,
            players=args.players,
            hands=args.hands,
            seed=args.seed,
            interactive=args.interactive,
        )
    )


if __name__ == "__main__":
    main()
