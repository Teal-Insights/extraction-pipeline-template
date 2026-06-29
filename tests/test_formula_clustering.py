from src.formula_clustering import levenshtein_ratio


def test_levenshtein_ratio_identical_strings() -> None:
    assert levenshtein_ratio("abc", "abc") == 0.0


def test_levenshtein_ratio_completely_different_lengths() -> None:
    assert levenshtein_ratio("", "abc") == 1.0
