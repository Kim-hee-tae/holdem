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


def test_side_pot_distribution_with_all_in():
    game = TexasHoldemGame(["A", "B", "C"], seed=3)
    a, b, c = game.players
    for p in game.players:
        p.reset_for_hand()

    # Contributions: A=50(all-in), B=100, C=100 (C folded)
    a.hand_contribution = 50
    b.hand_contribution = 100
    c.hand_contribution = 100
    game.pot = 250
    c.folded = True
    # A has stronger hand than B -> should win main pot 150, B gets side pot 100
    scored = [(a, (2, (14, 13, 12))), (b, (1, (10, 9, 8, 7)))]
    start_a, start_b = a.chips, b.chips

    winners = game._distribute_side_pots(scored)

    assert a.chips == start_a + 150
    assert b.chips == start_b + 100
    assert game.pot == 0
    assert {w.name for w in winners} == {"A", "B"}


def test_showdown_logs_reveal_all_hole_cards():
    game = TexasHoldemGame(["A", "B"], seed=5)
    game.start_hand()
    # Force immediate end by folding one player.
    game.players[1].folded = True
    game.showdown_or_award()
    joined = "\n".join(game.logs)
    assert "Hole cards reveal:" in joined
    assert "A:" in joined and "B:" in joined
