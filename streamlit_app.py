from __future__ import annotations

from collections import defaultdict

import httpx
import streamlit as st

from app.config import API_URL

st.set_page_config(page_title="Mini Hiring Pipeline", layout="wide")
st.title("Mini Hiring Pipeline")


def api(method: str, path: str, **kwargs):
    try:
        response = httpx.request(method, f"{API_URL}{path}", timeout=10, **kwargs)
        response.raise_for_status()
        return response.json(), None
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except ValueError:
            detail = exc.response.text or str(exc)
        return None, detail
    except httpx.HTTPError:
        return None, f"Cannot reach the API at {API_URL}. Start FastAPI first."


with st.sidebar:
    st.header("Add candidate")
    with st.form("add-candidate", clear_on_submit=True):
        name = st.text_input("Full name *")
        email = st.text_input("Email")
        notes = st.text_area("Notes")
        if st.form_submit_button("Add candidate"):
            if not name.strip(): st.error("A full name is required.")
            else:
                _, error = api("POST", "/candidates", json={"name": name, "email": email or None, "notes": notes or None})
                st.success("Candidate added.") if not error else st.error(error)

st.subheader("Find candidates")
with st.form("candidate-search", border=False):
    query = st.text_input("Search", type="search", placeholder="e.g. sharam and in Interview, or stuck in Screening for more than a week")
    search_submitted = st.form_submit_button("Search")
if search_submitted and query.strip():
    found, error = api("POST", "/search", json={"query": query})
    st.session_state.search_result = {"data": found, "error": error}

search_result = st.session_state.get("search_result")
if search_result:
    if search_result["error"]:
        st.error(search_result["error"])
    else:
        found = search_result["data"]
        if found["parser_source"] == "error":
            st.error(found["message"])
        else:
            (st.info if found["parser_source"] == "fallback" else st.caption)(found["message"])
            if found["interpretation"]: st.caption("Interpretation: " + str(found["interpretation"]))
            if not found["results"]: st.warning("No candidates match those filters.")
        for item in found["results"]:
            if st.button(f"{item['name']} — {item['current_stage']} ({item['days_in_stage']:.1f} days)", key=f"search-candidate-{item['id']}"):
                st.session_state.selected_candidate = item["id"]
                st.rerun()

data, api_error = api("GET", "/candidates")
if api_error:
    st.error(api_error)
else:
    st.subheader("Pipeline")
    groups = defaultdict(list)
    for item in data: groups[item["current_stage"]].append(item)
    stages = ["Applied", "Screening", "Interview", "Offer", "Hired", "Rejected"]
    columns = st.columns(len(stages))
    selected = None
    for column, stage in zip(columns, stages):
        with column:
            st.markdown(f"#### {stage}")
            for item in groups[stage]:
                if st.button(f"{item['name']} ({item['days_in_stage']:.0f}d)", key=f"candidate-{item['id']}"):
                    selected = item["id"]
    selected = selected or st.session_state.get("selected_candidate")
    if selected:
        st.session_state.selected_candidate = selected
        detail, error = api("GET", f"/candidates/{selected}")
        if error: st.error(error)
        else:
            st.divider(); st.subheader(detail["name"] + " — " + detail["current_stage"])
            st.caption(f"Current stage for {detail['days_in_stage']:.1f} days")
            if detail["current_stage"] not in ("Hired", "Rejected"):
                left, right = st.columns(2)
                if left.button("Advance one stage"):
                    _, action_error = api("POST", f"/candidates/{selected}/advance")
                    st.success("Candidate advanced.") if not action_error else st.error(action_error)
                    st.session_state.pop("search_result", None)
                    st.rerun()
                reason = right.text_input("Optional rejection reason", key=f"reason-{selected}")
                if right.button("Reject candidate"):
                    _, action_error = api("POST", f"/candidates/{selected}/reject", json={"reason": reason or None})
                    st.success("Candidate rejected.") if not action_error else st.error(action_error)
                    st.session_state.pop("search_result", None)
                    st.rerun()
            st.markdown("##### Immutable history")
            st.dataframe(detail["history"], width="stretch", hide_index=True)

with st.expander("AI search logs"):
    logs, error = api("GET", "/search/logs")
    if error: st.error(error)
    elif logs: st.dataframe(logs, width="stretch", hide_index=True)
    else: st.caption("No searches recorded yet.")
