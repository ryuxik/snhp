from intervals import merge


def test_classic_overlap():
    assert merge([[1, 3], [2, 6], [8, 10], [15, 18]]) == [[1, 6], [8, 10], [15, 18]]

def test_touching_merges():
    assert merge([[1, 4], [4, 5]]) == [[1, 5]]

def test_unsorted_input():
    assert merge([[5, 6], [1, 2]]) == [[1, 2], [5, 6]]

def test_nested():
    assert merge([[1, 10], [2, 3]]) == [[1, 10]]

def test_empty():
    assert merge([]) == []

def test_single():
    assert merge([[3, 7]]) == [[3, 7]]

def test_does_not_mutate_input():
    src = [[5, 6], [1, 2]]
    merge(src)
    assert src == [[5, 6], [1, 2]]

def test_all_disjoint_sorted():
    assert merge([[1, 2], [3, 4], [5, 6]]) == [[1, 2], [3, 4], [5, 6]]

def test_chain():
    assert merge([[1, 2], [2, 3], [3, 4]]) == [[1, 4]]
