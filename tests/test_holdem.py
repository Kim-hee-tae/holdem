from holdem import (
    Card,
    GameConfig,
    TexasHoldemGame,
    best_hand,
    evaluate_five,
)


def cards(spec: str):
    return [Card(rank=s[0], suit=s[1]) for s in spec.split()]


def test_straight_flush_beats_quads():
    sf = evaluate_five(cards("9S TS JS QS KS"))
    quads = evaluate_five(cards("AS AH AD AC 2D"))
    assert sf > quads


def test_wheel_straight():
    score = evaluate_five(cards("AS 2D 3C 4H 5S"))
    assert score[0] == 4
    assert score[1] == (5,)


def test_best_hand_from_seven_cards():
    seven = cards("AS AD AC KH KD 2S 3C")
    score, combo = best_hand(seven)
    assert score[0] == 6
    assert len(combo) == 5


def test_blinds_added_to_pot_on_hand_start():
    game = TexasHoldemGame(["A", "B", "C"], config=GameConfig(small_blind=5, big_blind=10), seed=7)
    game.start_hand()
    assert game.pot == 15


def test_apply_actions_fold_call_raise():
    game = TexasHoldemGame(["A", "B", "C"], seed=1)
    game.start_hand()
    a, b, c = game.players

    game.current_bet = 20
    a.current_bet = 0
    game.apply_action(a, "fold")
    assert a.folded

    b.current_bet = 0
    b_start = b.chips
    game.apply_action(b, "call")
    assert b.current_bet == 20
    assert b.chips == b_start - 20

    c.current_bet = 0
    game.apply_action(c, "raise", raise_to=40)
    assert game.current_bet >= 40


def test_tournament_finishes_with_single_player():
    game = TexasHoldemGame(
        ["A", "B"],
        config=GameConfig(mode="tournament", starting_stack=20, small_blind=5, big_blind=10),
        seed=2,
    )
    for _ in range(20):
        game.play_hand()
        if game.session_finished():
            break

    alive = [p for p in game.players if p.chips > 0]
    assert len(alive) == 1
