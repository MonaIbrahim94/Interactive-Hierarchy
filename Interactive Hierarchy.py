import pandas as pd
import plotly.express as px
import streamlit as st

# STREAMLIT CONFIG
st.set_page_config(layout="wide")
st.title("📊 Interactive Hierarchy Treemap with Search + Dependency Navigation")

# 1) FILE UPLOADER (for managers)

uploaded_file = st.file_uploader(
    "📂 Upload the Hierarchy Backend Excel file:",
    type=["xlsx"]
)

if uploaded_file is None:
    st.info("Please upload the Excel file to view the interactive hierarchy.")
    st.stop()

# 2) LOAD DATA (from uploaded Excel)

@st.cache_data
def load_data(file):
    hier_cols = [
        "Data Domain L1",
        "Business Process L1",
        "Business Process L2",
        "Data Domain L2",
        "Data Domain L3",
        "Use-case",
    ]

    df_h = pd.read_excel(file, sheet_name="Hierarchy", usecols=hier_cols)
    df_d = pd.read_excel(file, sheet_name="Dependencies")

    df_h = df_h.map(lambda x: x.strip() if isinstance(x, str) else x)
    df_d = df_d.map(lambda x: x.strip() if isinstance(x, str) else x)

    return df_h, df_d

df_h, df_d = load_data(uploaded_file)

# 3) BUILD PATHS (SKIP NaN)

def build_path(row):
    levels = [
        row["Data Domain L1"],
        row["Business Process L1"],
        row["Business Process L2"],
        row["Data Domain L2"],
        row["Data Domain L3"],
        row["Use-case"],
    ]
    return [lvl for lvl in levels if pd.notna(lvl) and lvl != ""]

df_h["path"] = df_h.apply(build_path, axis=1)

# 4) CREATE HIERARCHY NODES

nodes = {}

for path in df_h["path"]:
    for depth in range(len(path)):
        label = path[depth]
        node_id = " > ".join(path[:depth + 1])
        parent_id = " > ".join(path[:depth]) if depth > 0 else ""

        if node_id not in nodes:
            nodes[node_id] = {
                "id": node_id,
                "label": label,
                "parent": parent_id,
                "level": depth,
            }

nodes_df = pd.DataFrame(nodes.values())

# 5) MERGE DEPENDENCIES

deps_grouped = (
    df_d
    .dropna(subset=["Data Domain L3", "Data Domain L3 - Dependency"])
    .groupby("Data Domain L3")["Data Domain L3 - Dependency"]
    .apply(lambda x: ", ".join(sorted(set(x))))
    .reset_index(name="dependencies")
)

nodes_df = nodes_df.merge(
    deps_grouped,
    left_on="label",
    right_on="Data Domain L3",
    how="left"
).drop(columns=["Data Domain L3"])

nodes_df["dependencies"] = nodes_df["dependencies"].fillna("None")

# 6) ZOOM + DEPENDENCY HIGHLIGHTING

def get_ancestors(df, node_id):
    anc = []
    current = node_id
    while current:
        anc.append(current)
        parent = df.loc[df["id"] == current, "parent"].values[0]
        if parent == "" or parent is None:
            break
        current = parent
    return anc


def get_branch_with_dependencies(df, focus_id):
    df = df.copy()

    if focus_id is None:
        df["highlight"] = "Other"
        return df, [], []

    deps_raw = df.loc[df["id"] == focus_id, "dependencies"].values[0]
    dep_labels = [] if deps_raw == "None" else [d.strip() for d in deps_raw.split(",")]
    dep_ids = df[df["label"].isin(dep_labels)]["id"].tolist()

    ancestors = get_ancestors(df, focus_id)
    descendants = df[df["id"].str.startswith(focus_id)]["id"].tolist()
    branch_ids = set(ancestors) | set(descendants)

    dep_related_ids = set()
    for d in dep_ids:
        dep_related_ids.add(d)
        dep_related_ids.update(get_ancestors(df, d))

    visible_ids = branch_ids | dep_related_ids
    sub_df = df[df["id"].isin(visible_ids)].copy()

    def colorize(row):
        if row["id"] == focus_id:
            return "Clicked"
        elif row["id"] in dep_ids:
            return "Dependency"
        return "Other"

    sub_df["highlight"] = sub_df.apply(colorize, axis=1)
    return sub_df, dep_ids, dep_labels


def build_treemap(df):
    fig = px.treemap(
        df,
        ids="id",
        parents="parent",
        names="label",
        color="highlight",
        color_discrete_map={
            "Clicked": "#ff7f0e",
            "Dependency": "#d62728",
            "Other": "#aec7e8",
        },
        custom_data=["dependencies"]
    )

    fig.update_traces(
        hovertemplate="<b>%{label}</b><br>ID: %{id}<br>Depends on: %{customdata[0]}<extra></extra>"
    )
    return fig

# 7) STREAMLIT STATE

if "focus_node_id" not in st.session_state:
    st.session_state["focus_node_id"] = None

focus_id = st.session_state["focus_node_id"]

# SEARCH + RESET
c1, c2 = st.columns([3, 1])

with c1:
    search_term = st.text_input("🔍 Search:", placeholder="Promotions, Execution…")

with c2:
    if st.button("Reset view"):
        st.session_state["focus_node_id"] = None
        focus_id = None
        search_term = ""

if search_term and search_term.strip():
    matches = nodes_df[nodes_df["label"].str.contains(search_term, na=False, case=False)]
    if len(matches) > 0:
        focus_id = matches.iloc[0]["id"]
        st.session_state["focus_node_id"] = focus_id
        st.success(f"Zoomed to: {focus_id}")

# 8) BUILD FILTERED VIEW (ZOOM)

if focus_id:
    view_df, dep_ids, dep_labels = get_branch_with_dependencies(nodes_df, focus_id)
else:
    view_df = nodes_df.copy()
    view_df["highlight"] = "Other"
    dep_ids, dep_labels = [], []

fig = build_treemap(view_df)

# 9) CLICK HANDLER

plot_event = st.plotly_chart(fig, width="stretch", key="mainplot")
click_data = st.session_state.get("mainplot")

if isinstance(click_data, dict) and "points" in click_data:
    pts = click_data["points"]
    if pts:
        clicked_id = pts[0].get("id")
        if clicked_id:
            st.session_state["focus_node_id"] = clicked_id
            st.rerun()

# 10) INFO PANEL

if focus_id:
    st.subheader("📌 Selected Node")
    frow = nodes_df[nodes_df["id"] == focus_id].iloc[0]
    st.markdown(f"**Label:** `{frow['label']}`")
    st.markdown(f"**ID:** `{frow['id']}`")
    st.markdown(f"**Level:** `{frow['level']}`")
    st.markdown(f"**Dependencies:** `{frow['dependencies']}`")

    if dep_labels:
        st.write("### Dependent nodes highlighted in red:")
        st.write(", ".join(dep_labels))