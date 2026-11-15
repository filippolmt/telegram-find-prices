"""
make replay scores every post against candidate names with the matcher importable now.
"""

from replay import candidate_names, score_posts


def test_candidate_names_are_the_first_words_of_each_line():
    assert candidate_names("🎧 BOSE QuietComfort cuffie wireless\n📉 A 161,46€\nok") == {"bose quietcomfort cuffie", "a 161,46€"}


def test_score_rebuilds_hidden_links_and_prices_each_name():
    post = {
        "channel": "deals",
        "id": 1,
        "message": "TCL soundbar 340W\nA 79€\n\nBOSE QuietComfort cuffie\nA 161€ Apri link",
        "entities": [[len("TCL soundbar 340W\nA 79€\n\nBOSE QuietComfort cuffie\nA 161€ "), 9, "https://amzn.eu/d/x"]],
        "buttons": ["https://t.me/share/url?text=euro%20"],
    }
    scores = score_posts([post])
    assert scores["deals/1|tcl soundbar 340w"] == 79.0
    assert scores["deals/1|bose quietcomfort cuffie"] == 161.0
