from src.analysis import analyze, choose_chart, to_dataframe


def test_bar_chart_and_ranking():
    df = to_dataframe(["region", "revenue"], [("West", 150000.0), ("North", 120000.0), ("South", 95000.0)])
    chart = choose_chart(df)
    assert chart == {"type": "bar", "x": "region", "y": "revenue"}
    facts = analyze(df, chart)
    assert facts["highest"]["region"] == "West"
    assert facts["lowest"]["region"] == "South"
    assert facts["total"] == 365000.0
    assert facts["highest_share_percent"] == 41.1


def test_line_chart_for_months():
    df = to_dataframe(["month", "revenue"], [("2025-01", 100.0), ("2025-02", 150.0), ("2025-03", 120.0)])
    chart = choose_chart(df)
    assert chart["type"] == "line"
    facts = analyze(df, chart)
    assert facts["peak"]["month"] == "2025-02"
    assert facts["change_percent_first_to_last"] == 20.0


def test_no_chart_for_single_value():
    df = to_dataframe(["total_orders"], [(400,)])
    chart = choose_chart(df)
    assert chart["type"] == "none"
    assert analyze(df, chart)["single_value"]["value"] == 400


def test_count_is_not_mistaken_for_a_year():
    df = to_dataframe(["region", "orders"], [("West", 2024), ("East", 1500)])
    assert choose_chart(df)["type"] == "bar"


def test_empty_result():
    df = to_dataframe(["region", "revenue"], [])
    chart = choose_chart(df)
    assert chart["type"] == "none"
    assert analyze(df, chart) == {"row_count": 0}
