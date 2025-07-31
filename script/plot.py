import pandas as pd
import altair as alt
import fire
from pathlib import Path


from parse_log import parse_log
from altair_theme import jlhu_theme, COLUMN_WIDTH, DEFAULT_HEIGHT


WORKLOADS = [
    "liblinear",
    "silo",
    "btree",
    "xsbench",
    "graph500",
    "pagerank",
    "bwaves",
]
ORDERS = [
    "Demeter",
    "Memtis",
    "Nomad",
    "TPP",
    "TPP-H",
]


def find_workload_dir(base, keyword):
    base = Path(base)
    if not base.exists() or not base.is_dir():
        return None
    for item in base.iterdir():
        if item.is_dir() and keyword.lower() in item.name.lower():
            return item
    return None


def read_csv(data_dir, workload):
    dir = find_workload_dir(data_dir, workload)
    data = (
        parse_log(dir=dir)
        .rename(columns={workload: "elapsed"})
        .loc[:, ("vmnum", "design", "elapsed")]
    )
    return data


def preprocess(guest_log_dir, host_log_dir=None):
    merge = []
    for workload in WORKLOADS:
        guest = read_csv(guest_log_dir, workload)
        if host_log_dir:
            host = read_csv(host_log_dir, workload).replace("TPP", "TPP-H")
            data = pd.concat([guest, host], ignore_index=True)
        else:
            data = guest
        data["workload"] = workload
        agg = (
            data.groupby(["vmnum", "design"])
            .mean("elapsed")
            .groupby(level=0)
            .agg(["min", "max"])["elapsed"]
        )
        data = data.join(agg, on="vmnum")
        data["ratio"] = data["elapsed"] / data["min"]
        merge.append(data)
    return pd.concat(merge, ignore_index=True)


def plot(
    data,
    x="vmnum:N",
    y="elapsed:Q",
    color="design:N",
    domain=[0, 2300],
):
    def field(shorthand):
        return shorthand.split(":")[0]

    columns = 2
    metric = field(y)
    base = (
        alt.Chart()
        .transform_calculate(
            # https://github.com/vega/altair/issues/2220
            order=f"-indexof({ORDERS}, datum.{field(color)})"
        )
        .encode(
            x=alt.X(x)
            .title("Number of VMs")
            .scale(paddingInner=0.05, paddingOuter=0.1),
            xOffset=alt.XOffset(color),
            y=alt.Y(f"mean({metric}):Q")
            .title(None)
            .scale(
                clamp=True,
                domain=domain,
            ),
            text=alt.Text(
                "mean(ratio):Q",
                format=".01f",
            ),
            color=alt.Color(color)
            .sort(ORDERS)
            .legend(
                orient="none",
                titleOrient="top",
                direction="horizontal",
                title=None,
                legendX=135,
                legendY=235,
                labelLimit=70,
                columns=2,
            ),
            shape=alt.Shape(color).legend(None),
            order="order:Q",
            # order=alt.Order('color_site_sort_index:Q'),
        )
    )
    chart = (
        alt.layer(
            # base.mark_line(point=True).encode(),
            base.mark_bar().encode(),
            base.mark_errorbar(extent="stderr").encode(
                y=alt.Y(metric)
                .type("quantitative")
                .title("Elapsed Time (s)")
                .scale(zero=False),
            ),
            base.mark_text(
                baseline="middle",
                dx=7,
                fontSize=10,
                angle=270,
            ).encode(),
            data=data,
        )
        .properties(
            width=COLUMN_WIDTH / columns,
            height=DEFAULT_HEIGHT * 0.75,
        )
        .facet(
            facet=alt.Facet("workload:N").header(
                title="Elapsed Time (s)",
                titleOrient="left",
            ),
            columns=columns,
            spacing=dict(row=-3),
        )
    )
    return chart


def main(**kwargs):
    data = preprocess(**kwargs)
    chart = plot(data)
    chart.save("chart.svg")


if __name__ == "__main__":
    fire.Fire(main)
