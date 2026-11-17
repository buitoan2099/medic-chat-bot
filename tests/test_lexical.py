from rag.lexical import BM25Index, tokenize

from tests.conftest import make_chunk


def test_tokenize_unaccented_with_bigrams():
    assert tokenize('Chống chỉ định') == ['chong', 'chi', 'dinh', 'chong_chi', 'chi_dinh']


def _index():
    return BM25Index([
        make_chunk('a-c01', 'Amoxicilin › Chống chỉ định\nQuá mẫn với penicilin.', 'a', 1,
                   ['Amoxicilin', 'Chống chỉ định'], 'Chống chỉ định'),
        make_chunk('a-c02', 'Amoxicilin › Chỉ định\nNhiễm khuẩn đường hô hấp.', 'b', 1,
                   ['Amoxicilin', 'Chỉ định'], 'Chỉ định'),
        make_chunk('d-c01', 'Diclofenac › Chống chỉ định\nLoét dạ dày tiến triển.', 'c', 4,
                   ['Diclofenac', 'Chống chỉ định'], 'Chống chỉ định'),
        make_chunk('d-c02', 'Diclofenac › Chống chỉ định\nSuy tim nặng.', 'c', 4,
                   ['Diclofenac', 'Chống chỉ định'], 'Chống chỉ định'),
    ])


def test_search_ranks_exact_drug_and_phrase_first():
    index = _index()
    top = index.chunks[index.search('chống chỉ định của amoxicilin', 3)[0][0]]
    assert top['id'] == 'a-c01'


def test_unaccented_query_matches_accented_text():
    index = _index()
    hits = index.search('loet da day', 2)
    assert index.chunks[hits[0][0]]['id'] == 'd-c01'


def test_unknown_terms_return_nothing():
    assert _index().search('xyzzy', 5) == []


def test_node_docs_groups_chunks_of_same_section_in_order():
    index = _index()
    assert [index.chunks[i]['id'] for i in index.node_docs['c']] == ['d-c01', 'd-c02']
