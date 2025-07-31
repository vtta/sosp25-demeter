import altair as alt

# alt.renderers.enable("jupyter", offline=False)
# alt.data_transformers.enable("vegafusion")

PPI = 72
COLUMN_WIDTH = PPI * (7 - 1 / 3) / 2
PARENT_WIDTH = PPI * 7
DEFAULT_HEIGHT = PPI * 1


@alt.theme.register("jlhu_theme", enable=True)
def jlhu_theme() -> alt.theme.ThemeConfig:
    return {
        "config": {
            "padding": 2,
            "font": "Libertinus Serif",
            "view": {
                "continuousWidth": COLUMN_WIDTH,
                "continuousHeight": DEFAULT_HEIGHT,
                "stroke": "black",
                "strokeWidth": 1,
            },
            "bar": {"stroke": "black", "strokeWidth": 1},
            "legend": {
                "gradientStrokeColor": "black",
                "gradientStrokeWidth": 1,
                "symbolStrokeColor": "black",
                "symbolStrokeWidth": 1,
                "offset": 5,
                "padding": 0,
                "columnPadding": 0,
                "rowPadding": 0,
                "labelLimit": 50,
                "titleLimit": 50,
                "orient": "top",
                "titleOrient": "left",
                "titleAnchor": "start",
                "direction": "horizontal",
                "title": None,
                "titleFontSize": 10,
                "labelFontSize": 10,
            },
            "axis": {
                "labelFontSize": 10,
                "titleFontSize": 10,
                "grid": False,
                "domainColor": "black",
                "domainWidth": 1,
                "tickColor": "black",
                "tickWidth": 1,
                "tickSize": 3,
            },
            "axisX": {"labelAngle": 0},
            "axisY": {"titlePadding": 0},
            "facet": {"spacing": 0},
            "header": {"titlePadding": 0, "labelPadding": 0},
        }
    }
