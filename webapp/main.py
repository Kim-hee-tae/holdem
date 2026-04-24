from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from holdem import Action, GameConfig, Player, TexasHoldemGame


class PlayRequest(BaseModel):
    action: Literal["fold", "check", "call", "raise"] = "call"
    raise_to: int | None = None


class WebSession:
    def __init__(self, seed: int | None = None) -> None:
        self.game = TexasHoldemGame(
            ["You", "Bot1", "Bot2", "Bot3"],
            config=GameConfig(mode="cash"),
            seed=seed,
            human_player="You",
        )
        self.action: Action = "call"
        self.raise_to: int | None = None

    def prompt(self, player: Player, to_call: int) -> tuple[Action, int]:
        if self.action == "fold" and to_call > 0:
            return "fold", 0
        if self.action == "check" and to_call == 0:
            return "check", 0
        if self.action == "raise":
            target = self.raise_to if self.raise_to is not None else self.game.current_bet + self.game.config.big_blind
            return "raise", target
        if to_call == 0:
            return "check", 0
        return "call", 0

    def play_once(self, action: Action, raise_to: int | None) -> None:
        self.action = action
        self.raise_to = raise_to
        original = self.game._prompt_human_action
        self.game._prompt_human_action = self.prompt  # type: ignore[assignment]
        self.game.play_hand()
        self.game._prompt_human_action = original  # type: ignore[assignment]

    def state(self) -> dict:
        return {
            "logs": self.game.logs,
            "standings": self.game.standings(),
            "hand_no": self.game.hand_no,
            "players": [
                {
                    "name": p.name,
                    "chips": p.chips,
                    "folded": p.folded,
                    "all_in": p.all_in,
                    "current_bet": p.current_bet,
                }
                for p in self.game.players
            ],
        }


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
        session.play_once(req.action, req.raise_to)
        return session.state()

    return app
