"""Quick tests for visualization recommendation logic."""

from agent.core.viz_recommender import VizRecommender


def test_recommend_metric_card_single_numeric_value() -> None:
    """A single-row single-metric result should render as a metric card."""
    recommender = VizRecommender()
    sql = "SELECT SUM(revenue) AS total_revenue FROM orders"
    results = [{"total_revenue": 12345.67}]
    column_types = {"total_revenue": "numeric"}

    config = recommender.recommend(sql=sql, results=results, column_types=column_types)

    assert config.chart_type == "metric_card"
    assert config.y_axis == "total_revenue"
    assert config.format_hints.get("total_revenue") == "currency"
