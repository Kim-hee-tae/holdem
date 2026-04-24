from holdem import Card, evaluate_five, best_hand


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
