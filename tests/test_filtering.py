import vea.utils.filtering as filt


def test_filter_documents_tfidf_returns_most_relevant():
    docs = [
        "Discuss project Alpha next week",
        "Grocery list: milk, eggs, bread",
        "Meeting notes about project Beta",
    ]
    topics = ["project Alpha kickoff"]

    result = filt.filter_documents(docs, topics, top_n=1)
    assert result == [docs[0]]


def test_filter_documents_keyword_threshold():
    docs = [
        "Remember to buy apples",
        "Schedule meeting with team",
    ]
    topics = ["apples", "oranges"]

    result = filt.filter_documents(docs, topics, ranker=filt.KeywordRanker(), threshold=0.1)
    assert result == [docs[0]]


def test_pipeline_limits_and_ranks():
    docs = [
        {"id": "1", "type": "journal", "content": "Alpha project update"},
        {"id": "2", "type": "note", "content": "Random thoughts"},
        {"id": "3", "type": "email", "content": "Alpha meeting tomorrow"},
    ]
    topics = ["Alpha meeting"]

    pipe = filt.RelevanceFilterPipeline(max_documents=2)
    result = pipe.filter(docs, topics)

    assert len(result["documents"]) == 2
    assert result["documents"][0]["id"] == "3"  # email mentioning meeting should rank highest


def test_pipeline_with_custom_strategy():
    docs = [
        {"id": "1", "type": "note", "content": "Buy milk"},
        {"id": "2", "type": "journal", "content": "Meeting about Beta"},
    ]
    topics = ["milk"]

    pipe = filt.RelevanceFilterPipeline(strategies=[filt.KeywordMatchStrategy()])
    result = pipe.filter(docs, topics)

    assert result["documents"][0]["id"] == "1"


def test_run_pipeline_helper():
    docs = [
        {"id": "1", "type": "note", "content": "Discuss Alpha"},
        {"id": "2", "type": "note", "content": "Discuss Beta"},
    ]
    topics = ["Alpha"]

    result = filt.run_pipeline(docs, topics, max_documents=1)

    assert result["documents"][0]["id"] == "1"


def test_pipeline_respects_token_budget():
    docs = [
        {"id": "1", "type": "note", "content": "Alpha project " * 20},
        {"id": "2", "type": "note", "content": "Beta project " * 20},
    ]
    topics = ["Alpha project"]

    result = filt.run_pipeline(docs, topics, token_budget=80)

    assert result["total_tokens"] <= 80
    assert len(result["documents"]) == 1
    assert result["documents"][0]["id"] == "1"


def test_return_scores_and_weighting():
    docs = [
        {"id": "1", "type": "note", "content": "Alpha Beta"},
    ]
    topics = ["Alpha"]

    pipe = filt.RelevanceFilterPipeline(
        strategies=[(filt.TFIDFStrategy(preprocess=False), 0.7), (filt.KeywordMatchStrategy(preprocess=False), 0.3)],
        max_documents=1,
    )
    result = pipe.filter(docs, topics, return_scores=True)

    doc = result["documents"][0]
    tfidf = doc["strategy_scores"]["TFIDFStrategy"]
    kw = doc["strategy_scores"]["KeywordMatchStrategy"]
    expected = tfidf * 0.7 + kw * 0.3
    assert abs(doc["combined_score"] - expected) < 1e-6


class CountStrategy(filt.RelevanceStrategy):
    def score(self, doc: str, topics: list[str]) -> float:
        doc_tokens = set(self._prep(doc))
        topic_tokens = set(self._prep(" ".join(topics)))
        return len(doc_tokens & topic_tokens)


def test_score_normalization_and_weighting():
    docs = [{"id": "1", "type": "note", "content": "alpha beta gamma"}]
    topics = ["alpha beta"]

    pipe = filt.RelevanceFilterPipeline(
        strategies=[(CountStrategy(preprocess=False), 0.5), (filt.KeywordMatchStrategy(preprocess=False), 0.5)],
        max_documents=1,
    )
    result = pipe.filter(docs, topics, return_scores=True)
    doc = result["documents"][0]
    count_sc = doc["strategy_scores"]["CountStrategy"]
    kw_sc = doc["strategy_scores"]["KeywordMatchStrategy"]
    expected = count_sc * 0.5 + kw_sc * 0.5
    assert count_sc == 1.0  # normalized from raw count 2
    assert abs(doc["combined_score"] - expected) < 1e-6


def test_token_budget_skips_large_doc():
    docs = [
        {"id": "1", "type": "note", "content": "big " * 100},
        {"id": "2", "type": "note", "content": "small relevant"},
    ]
    topics = ["relevant"]

    result = filt.run_pipeline(docs, topics, token_budget=20)

    assert len(result["documents"]) == 1
    assert result["documents"][0]["id"] == "2"

