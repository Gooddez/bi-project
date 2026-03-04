"""
chart_builder.py — Deterministic Altair chart builder.
Takes a chart config JSON from chart_agent and a pandas DataFrame,
returns an Altair chart as a JSON spec string.

Supports 10 chart types:
  bar, hbar, line, area, scatter, pie, heatmap, boxplot, histogram, bubble
"""

import json
import pandas as pd
import altair as alt
from typing import Optional

# ─── Pastel chart config ──────────────────────────────────────────────────────

PASTEL_SCHEMES = {
    "categorical": "pastel1",
    "sequential":  "purples",
    "diverging":   "redblue",
}

BASE_PROPS = dict(width=860, height=400, padding={"left": 20, "right": 20, "top": 16, "bottom": 16})

def _base_config(chart: alt.Chart) -> alt.Chart:
    return (
        chart
        .properties(**BASE_PROPS)
        .configure_view(strokeWidth=0, fill="#ffffff")
        .configure_axis(
            labelColor="#6b7280", titleColor="#374151",
            gridColor="#f3f4f6", gridOpacity=1,
            domainColor="#e5e7eb", tickColor="#e5e7eb",
            labelFontSize=11, labelPadding=8, titlePadding=12,
            labelFont="Plus Jakarta Sans", titleFont="Plus Jakarta Sans",
        )
        .configure_legend(
            labelColor="#6b7280", titleColor="#374151",
            labelFontSize=11, titleFontSize=11,
            labelFont="Plus Jakarta Sans", titleFont="Plus Jakarta Sans",
            orient="bottom", columns=4,
        )
        .configure_title(
            font="Plus Jakarta Sans", fontSize=14,
            color="#1e1b4b", anchor="start",
        )
    )


def _infer_type(df: pd.DataFrame, col: str) -> str:
    """Return Altair type shorthand: :Q, :N, :T, :O"""
    if col not in df.columns:
        return ":N"
    dtype = df[col].dtype
    if pd.api.types.is_numeric_dtype(dtype):
        return ":Q"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return ":T"
    return ":N"


# ─── Individual chart builders ────────────────────────────────────────────────

def _bar(df, x, y, color, title):
    c = color or x
    return _base_config(
        alt.Chart(df, title=title).mark_bar(
            cornerRadiusTopLeft=3, cornerRadiusTopRight=3
        ).encode(
            x=alt.X(x + ":N", title=x.replace("_", " "), axis=alt.Axis(labelAngle=-35)),
            y=alt.Y(y + ":Q", title=y.replace("_", " ")),
            color=alt.Color(c + ":N", scale=alt.Scale(scheme=PASTEL_SCHEMES["categorical"]), legend=None),
            tooltip=list({x, y, c} & set(df.columns)),
        )
    )


def _hbar(df, x, y, color, title):
    c = color or x
    return _base_config(
        alt.Chart(df, title=title).mark_bar(
            cornerRadiusTopRight=3, cornerRadiusBottomRight=3
        ).encode(
            y=alt.Y(x + ":N", sort="-x", title=x.replace("_", " ")),
            x=alt.X(y + ":Q", title=y.replace("_", " ")),
            color=alt.Color(c + ":N", scale=alt.Scale(scheme=PASTEL_SCHEMES["categorical"]), legend=None),
            tooltip=list({x, y, c} & set(df.columns)),
        )
    )


def _line(df, x, y, color, title, sort_x=None):
    # Sort by Calendar_Month_ISO if available (guaranteed correct chronological order)
    # then pass explicit list to Altair — because sort=None in Altair means alphabetical, NOT row order
    if "Calendar_Month_ISO" in df.columns and x != "Calendar_Month_ISO":
        df = df.sort_values("Calendar_Month_ISO")
    x_order = list(df[x].astype(str)) if x in df.columns else None
    encode_args = dict(
        x=alt.X(x + ":N", sort=x_order, title=x.replace("_", " "), axis=alt.Axis(labelAngle=-45)),
        y=alt.Y(y + ":Q", title=y.replace("_", " ")),
        tooltip=list({x, y} & set(df.columns)),
    )
    if color and color in df.columns:
        encode_args["color"] = alt.Color(color + ":N", scale=alt.Scale(scheme=PASTEL_SCHEMES["categorical"]))

    line   = alt.Chart(df, title=title).mark_line(strokeWidth=2.5).encode(**encode_args)
    points = alt.Chart(df).mark_point(filled=True, size=55).encode(**encode_args)
    return _base_config((line + points).properties(**BASE_PROPS))


def _area(df, x, y, color, title, sort_x=None):
    if "Calendar_Month_ISO" in df.columns and x != "Calendar_Month_ISO":
        df = df.sort_values("Calendar_Month_ISO")
    x_order = list(df[x].astype(str)) if x in df.columns else None
    encode_args = dict(
        x=alt.X(x + ":N", sort=x_order, title=x.replace("_", " "), axis=alt.Axis(labelAngle=-45)),
        y=alt.Y(y + ":Q", title=y.replace("_", " ")),
        tooltip=list({x, y} & set(df.columns)),
    )
    if color and color in df.columns:
        encode_args["color"] = alt.Color(color + ":N", scale=alt.Scale(scheme=PASTEL_SCHEMES["categorical"]))

    return _base_config(
        alt.Chart(df, title=title).mark_area(opacity=0.6, line={"strokeWidth": 2}).encode(**encode_args)
    )


def _scatter(df, x, y, color, title):
    encode_args = dict(
        x=alt.X(x + ":Q", title=x.replace("_", " ")),
        y=alt.Y(y + ":Q", title=y.replace("_", " ")),
        tooltip=list({x, y} & set(df.columns)),
    )
    if color and color in df.columns:
        encode_args["color"] = alt.Color(color + ":N", scale=alt.Scale(scheme=PASTEL_SCHEMES["categorical"]))

    return _base_config(
        alt.Chart(df, title=title).mark_circle(size=90, opacity=0.75).encode(**encode_args)
    )


def _pie(df, x, y, title):
    return _base_config(
        alt.Chart(df, title=title).mark_arc(innerRadius=60, outerRadius=140).encode(
            theta=alt.Theta(y + ":Q"),
            color=alt.Color(x + ":N", scale=alt.Scale(scheme=PASTEL_SCHEMES["categorical"])),
            tooltip=[x, y],
        )
    )


def _heatmap(df, x, x2, y, title):
    return _base_config(
        alt.Chart(df, title=title).mark_rect(cornerRadius=2).encode(
            x=alt.X(x + ":N",  title=x.replace("_",  " ")),
            y=alt.Y(x2 + ":N", title=x2.replace("_", " ")),
            color=alt.Color(y + ":Q", scale=alt.Scale(scheme=PASTEL_SCHEMES["sequential"]), title=y.replace("_", " ")),
            tooltip=[x, x2, y],
        )
    )


def _boxplot(df, x, y, title):
    return _base_config(
        alt.Chart(df, title=title).mark_boxplot(extent="min-max", ticks=True).encode(
            x=alt.X(x + ":N", title=x.replace("_", " ")),
            y=alt.Y(y + ":Q", title=y.replace("_", " ")),
            color=alt.Color(x + ":N", scale=alt.Scale(scheme=PASTEL_SCHEMES["categorical"]), legend=None),
        )
    )


def _histogram(df, x, title):
    return _base_config(
        alt.Chart(df, title=title).mark_bar(
            cornerRadiusTopLeft=2, cornerRadiusTopRight=2,
            color="#c4b5fd",
        ).encode(
            x=alt.X(x + ":Q", bin=alt.Bin(maxbins=20), title=x.replace("_", " ")),
            y=alt.Y("count():Q", title="Count"),
            tooltip=[alt.Tooltip(x + ":Q", bin=True), "count():Q"],
        )
    )


def _bubble(df, x, y, size, color, title):
    encode_args = dict(
        x=alt.X(x + ":Q", title=x.replace("_", " ")),
        y=alt.Y(y + ":Q", title=y.replace("_", " ")),
        size=alt.Size(size + ":Q", scale=alt.Scale(range=[50, 1200])),
        tooltip=list({x, y, size} & set(df.columns)),
    )
    if color and color in df.columns:
        encode_args["color"] = alt.Color(color + ":N", scale=alt.Scale(scheme=PASTEL_SCHEMES["categorical"]))

    return _base_config(
        alt.Chart(df, title=title).mark_circle(opacity=0.75).encode(**encode_args)
    )


# ─── Public entry point ───────────────────────────────────────────────────────

def build_chart(config: dict, df: pd.DataFrame) -> Optional[str]:
    """
    Build an Altair chart from agent config + DataFrame.
    Returns Vega-Lite JSON string, or None if chart can't be built.
    """
    if df is None or len(df) == 0:
        return None

    chart_type = config.get("chart_type", "bar")
    title      = config.get("title", "")
    x          = config.get("x") or ""
    y          = config.get("y") or ""
    color      = config.get("color")
    size       = config.get("size")
    x2         = config.get("x2")
    sort_x     = config.get("sort_x")   # "data" = preserve row order (time series)

    cols = set(df.columns)

    # Validate required columns exist
    if chart_type in ("bar", "hbar", "line", "area", "scatter", "pie", "boxplot") and (x not in cols or y not in cols):
        # fallback: pick first string col as x, first numeric as y
        str_cols = [c for c in df.columns if df[c].dtype == object]
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        x = str_cols[0] if str_cols else df.columns[0]
        y = num_cols[0] if num_cols else df.columns[-1]
        chart_type = "hbar"

    try:
        if chart_type == "bar":
            chart = _bar(df, x, y, color, title)
        elif chart_type == "hbar":
            chart = _hbar(df, x, y, color, title)
        elif chart_type == "line":
            chart = _line(df, x, y, color, title)
        elif chart_type == "area":
            chart = _area(df, x, y, color, title)
        elif chart_type == "scatter":
            chart = _scatter(df, x, y, color, title)
        elif chart_type == "pie":
            chart = _pie(df, x, y, title)
        elif chart_type == "heatmap":
            _x2 = x2 if x2 and x2 in cols else ([c for c in df.columns if c != x and df[c].dtype == object] + [x])[0]
            chart = _heatmap(df, x, _x2, y, title)
        elif chart_type == "boxplot":
            chart = _boxplot(df, x, y, title)
        elif chart_type == "histogram":
            _hx = x if x in cols else ([c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])] + [df.columns[0]])[0]
            chart = _histogram(df, _hx, title)
        elif chart_type == "bubble":
            _size = size if size and size in cols else y
            chart = _bubble(df, x, y, _size, color, title)
        else:
            chart = _hbar(df, x, y, color, title)

        return chart.to_json()

    except Exception as e:
        print(f"[CHART BUILD ERROR] {e}")
        # Last-resort fallback: simple horizontal bar
        try:
            str_cols = [c for c in df.columns if df[c].dtype == object]
            num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
            if str_cols and num_cols:
                chart = _hbar(df, str_cols[0], num_cols[0], None, title)
                return chart.to_json()
        except Exception:
            pass
        return None