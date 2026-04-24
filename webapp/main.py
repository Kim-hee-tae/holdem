from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from holdem import Action, GameConfig, TexasHoldemGame


class PlayRequest(BaseModel):
    action: Literal["fold", "check", "call", "raise", "next_round"] = "call"
    raise_to: int | None = None


WebAction = Literal["fold", "check", "call", "raise", "next_round"]


class TurnEngine:
    """WebSocket turn-based driver for one table with one human seat (You)."""

    def __init__(self, seed: int | None = None) -> None:
        self.game = TexasHoldemGame(
            ["You", "Bot1", "Bot2", "Bot3"],
            config=GameConfig(mode="cash"),
            seed=seed,
            human_player=None,
        )
        self.human_idx = 0
        self.phase = "idle"
        self.round_waiting: set[int] = set()
        self.current_idx = 0
        self.last_prompt: dict | None = None

    def _next(self, idx: int) -> int:
        return (idx + 1) % len(self.game.players)

    def _eligible(self, idx: int) -> bool:
        p = self.game.players[idx]
        return not p.folded and not p.all_in

    def _init_round(self, start_idx: int) -> None:
        self.current_idx = start_idx
        self.round_waiting = {i for i, _ in enumerate(self.game.players) if self._eligible(i)}

    def _find_next_waiting(self, from_idx: int) -> int | None:
        idx = from_idx
        for _ in range(len(self.game.players)):
            if idx in self.round_waiting and self._eligible(idx):
                return idx
            idx = self._next(idx)
        return None

    def _street_start_idx(self) -> int:
        if self.phase == "preflop":
            return self.game._next_index(self.game._next_index(self.game._next_index(self.game.dealer_idx)))
        return self.game._next_index(self.game.dealer_idx)

    def start_hand(self) -> dict:
        self.game.start_hand()
        self.phase = "preflop"
        self._init_round(self._street_start_idx())
        self.last_prompt = None
        return self.snapshot("hand_started")

    def snapshot(self, event: str, **extra: object) -> dict:
        data = {
            "event": event,
            "phase": self.phase,
            "pot": self.game.pot,
            "board": self.game.format_cards(self.game.board),
            "board_cards": [str(c) for c in self.game.board],
            "logs": self.game.logs,
            "standings": self.game.standings(),
            "players": [
                {
                    "name": p.name,
                    "chips": p.chips,
                    "current_bet": p.current_bet,
                    "folded": p.folded,
                    "all_in": p.all_in,
                }
                for p in self.game.players
            ],
            "you_cards": [str(c) for c in self.game.players[self.human_idx].hole_cards],
        }
        data.update(extra)
        return data

    def _advance_street(self) -> dict | None:
        if self.phase == "preflop":
            self.game._reset_bets()
            self.game.deal_flop()
            self.phase = "flop"
            self._init_round(self._street_start_idx())
            return self.snapshot("street_changed")
        if self.phase == "flop":
            self.game._reset_bets()
            self.game.deal_turn()
            self.phase = "turn"
            self._init_round(self._street_start_idx())
            return self.snapshot("street_changed")
        if self.phase == "turn":
            self.game._reset_bets()
            self.game.deal_river()
            self.phase = "river"
            self._init_round(self._street_start_idx())
            return self.snapshot("street_changed")
        if self.phase == "river":
            self.phase = "showdown"
            winners = self.game.showdown_or_award()
            self.game.rotate_dealer()
            self.phase = "finished"
            return self.snapshot(
                "hand_finished",
                winners=[w.name for w in winners],
                revealed_cards={
                    p.name: [str(c) for c in p.hole_cards]
                    for p in self.game.players
                },
            )
        return None

    def advance_until_human_or_end(self) -> dict:
        while True:
            if not self.game._can_continue():
                winners = self.game.showdown_or_award()
                self.game.rotate_dealer()
                self.phase = "finished"
                return self.snapshot(
                    "hand_finished",
                    winners=[w.name for w in winners],
                    revealed_cards={
                        p.name: [str(c) for c in p.hole_cards]
                        for p in self.game.players
                    },
                )

            if not self.round_waiting:
                changed = self._advance_street()
                if changed and changed["event"] == "hand_finished":
                    return changed
                continue

            idx = self._find_next_waiting(self.current_idx)
            if idx is None:
                self.round_waiting.clear()
                continue

            self.current_idx = self._next(idx)
            player = self.game.players[idx]
            to_call = max(0, self.game.current_bet - player.current_bet)

            if idx == self.human_idx:
                allowed = ["fold", "call", "raise"] if to_call > 0 else ["check", "raise"]
                self.last_prompt = {"player": player.name, "to_call": to_call, "allowed": allowed}
                return self.snapshot("action_required", prompt=self.last_prompt)

            action, raise_to = self.game.decide_action(player)
            self._apply_action_indexed(idx, action, raise_to)

    def _apply_action_indexed(self, idx: int, action: Action, raise_to: int) -> None:
        player = self.game.players[idx]
        self.game.apply_action(player, action, raise_to)
        if idx in self.round_waiting:
            self.round_waiting.remove(idx)

        if action == "raise":
            self.round_waiting = {
                i
                for i, _ in enumerate(self.game.players)
                if i != idx and self._eligible(i)
            }

    def apply_human_action(self, action: Action, raise_to: int | None = None) -> dict:
        if self.phase != "preflop" and self.phase not in {"flop", "turn", "river"}:
            return self.snapshot("error", message="No active hand")

        idx = self.human_idx
        if idx not in self.round_waiting:
            return self.snapshot("error", message="Human action not expected now")

        player = self.game.players[idx]
        to_call = max(0, self.game.current_bet - player.current_bet)
        allowed = {"fold", "call", "raise"} if to_call > 0 else {"check", "raise"}
        if action not in allowed:
            return self.snapshot(
                "error",
                message=f"Invalid action '{action}' for to_call={to_call}. Allowed={sorted(allowed)}",
                prompt={"player": player.name, "to_call": to_call, "allowed": sorted(allowed)},
            )

        raise_target = raise_to if raise_to is not None else self.game.current_bet + self.game.config.big_blind
        self._apply_action_indexed(idx, action, raise_target)
        self.last_prompt = None
        return self.advance_until_human_or_end()


class WebSession:
    def __init__(self, seed: int | None = None) -> None:
        self.turn = TurnEngine(seed=seed)
        self.last_state = self.turn.start_hand()

    def state(self) -> dict:
        return self.last_state

    def play_once(self, action: WebAction, raise_to: int | None) -> dict:
        if action == "next_round":
            self.last_state = self.turn.start_hand()
            self.last_state = self.turn.advance_until_human_or_end()
            return self.last_state

        self.last_state = self.turn.apply_human_action(action, raise_to)
        return self.last_state


def create_app(seed: int | None = None) -> FastAPI:
    app = FastAPI(title="Holdem Web API")
    session = WebSession(seed=seed)

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/state")
    def get_state() -> dict:
        return session.state()

    @app.post("/api/play")
    def play(req: PlayRequest) -> dict:
        return session.play_once(req.action, req.raise_to)

    @app.websocket("/ws")
    async def ws_turn(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            await websocket.send_json(session.state())
            while True:
                msg = await websocket.receive_json()
                action = msg.get("action", "call")
                raise_to = msg.get("raise_to")
                state = session.play_once(action, raise_to)
                await websocket.send_json(state)
        except WebSocketDisconnect:
            return

    return app
