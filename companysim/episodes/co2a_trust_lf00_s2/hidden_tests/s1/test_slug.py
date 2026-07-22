from slug import slugify


def test_basic():
    assert slugify("Hello, World!") == "hello-world"

def test_underscores_and_trim():
    assert slugify("  Foo___Bar  ") == "foo-bar"

def test_collapse_spaces():
    assert slugify("a  b") == "a-b"

def test_symbols_collapse():
    assert slugify("C++ Rocks!") == "c-rocks"

def test_already_slug():
    assert slugify("already-slug") == "already-slug"

def test_mixed_case_digits():
    assert slugify("MiXeD123") == "mixed123"

def test_all_separators():
    assert slugify("---") == ""

def test_empty():
    assert slugify("") == ""

def test_no_double_hyphen():
    out = slugify("a - - b")
    assert "--" not in out
    assert out == "a-b"

def test_leading_trailing_symbols():
    assert slugify("!!!hi!!!") == "hi"
