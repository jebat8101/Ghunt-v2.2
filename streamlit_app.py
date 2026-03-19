"""
GHunt Streamlit UI — lightweight lookups using the same APIs as the examples/ scripts.

Prerequisites:
  - pip install -r requirements-streamlit.txt
  - Run `ghunt login` once so credentials exist for People API lookups.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import streamlit as st

# Ensure package root is on path when launched as `streamlit run streamlit_app.py`
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ghunt.apis.peoplepa import PeoplePaHttp
from ghunt.helpers.gmail import is_email_registered
from ghunt.objects.base import GHuntCreds


def _run(coro):
    return asyncio.run(coro)


async def _lookup_display_name(email: str) -> tuple[bool, str | None]:
    ghunt_creds = GHuntCreds()
    ghunt_creds.load_creds()
    async with httpx.AsyncClient() as client:
        api = PeoplePaHttp(ghunt_creds)
        found, person = await api.people_lookup(
            client, email.strip(), params_template="just_name"
        )
        if not found:
            return False, None
        if "PROFILE" in person.names:
            return True, person.names["PROFILE"].fullname
        return True, None


async def _registered(email: str) -> bool:
    async with httpx.AsyncClient() as client:
        return await is_email_registered(client, email.strip())


st.set_page_config(
    page_title="GHunt",
    page_icon="🔎",
    layout="centered",
)

st.title("GHunt")
st.caption("Use only on targets you are authorized to investigate.")

tab_name, tab_reg, tab_about = st.tabs(
    ["Display name lookup", "Gmail / Google account?", "About"]
)

with tab_name:
    st.markdown("Resolve **public PROFILE** display name for an email (People API).")
    email_a = st.text_input("Email", key="name_email", placeholder="user@gmail.com")
    if st.button("Look up name", key="btn_name"):
        if not email_a.strip():
            st.warning("Enter an email address.")
        else:
            with st.spinner("Querying…"):
                try:
                    found, name = _run(_lookup_display_name(email_a))
                except Exception as e:
                    st.error(f"Request failed: `{e}`")
                    st.info("Try `ghunt login` if credentials are missing or expired.")
                else:
                    if not found:
                        st.error("Not found via People lookup.")
                    elif name:
                        st.success(name)
                    else:
                        st.warning(
                            "Found, but no **PROFILE** container / public name "
                            "(may exist only in contacts or restricted)."
                        )

with tab_reg:
    st.markdown("Check whether the address appears **registered with Google** (lightweight probe).")
    email_b = st.text_input("Email", key="reg_email", placeholder="user@gmail.com")
    if st.button("Check registration", key="btn_reg"):
        if not email_b.strip():
            st.warning("Enter an email address.")
        else:
            with st.spinner("Checking…"):
                try:
                    reg = _run(_registered(email_b))
                except Exception as e:
                    st.error(f"Request failed: `{e}`")
                else:
                    st.success("Registered with Google.") if reg else st.info(
                        "Not registered (or probe inconclusive)."
                    )

with tab_about:
    st.markdown(
        """
        - **Full OSINT hunt** (maps, calendar, games, JSON export): use the CLI  
          `ghunt email <address> [--json out.json]`
        - **Auth**: `ghunt login`
        - Source examples: `examples/get_people_name.py`, `examples/email_registered.py`
        """
    )
