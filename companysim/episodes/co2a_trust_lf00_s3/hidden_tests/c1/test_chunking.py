import pytest
from chunking import chunk


def test_uneven_remainder():
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]

def test_even():
    assert chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]

def test_size_larger_than_list():
    assert chunk([1, 2, 3], 5) == [[1, 2, 3]]

def test_empty():
    assert chunk([], 3) == []

def test_single():
    assert chunk([1], 1) == [[1]]

def test_size_zero_raises():
    with pytest.raises(ValueError):
        chunk([1, 2, 3], 0)

def test_size_negative_raises():
    with pytest.raises(ValueError):
        chunk([1, 2, 3], -2)

def test_does_not_mutate_input():
    src = [1, 2, 3, 4, 5]
    chunk(src, 2)
    assert src == [1, 2, 3, 4, 5]

def test_three_full():
    assert chunk([1, 2, 3, 4, 5, 6], 3) == [[1, 2, 3], [4, 5, 6]]
