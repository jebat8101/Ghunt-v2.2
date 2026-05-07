"""
GHunt Streamlit UI — lightweight lookups using the same APIs as the examples/ scripts.

Prerequisites:
  - pip install -r requirements-streamlit.txt
  - Run `ghunt login` once so credentials exist for People API lookups.
"""

from __future__ import annotations

import asyncio
import subprocess
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
from ghunt.parsers.people import Person


def _run(coro):
    return asyncio.run(coro)


def _best_name_from_person(person: Person) -> tuple[str | None, list[str]]:
    containers = sorted(person.names.keys()) if person.names else []
    if "PROFILE" in person.names:
        p = person.names["PROFILE"]
        for candidate in (p.fullname, f"{p.firstName} {p.lastName}".strip()):
            if candidate and candidate.strip():
                return candidate.strip(), containers
    for container in containers:
        entry = person.names.get(container)
        if not entry:
            continue
        if getattr(entry, "fullname", None) and str(entry.fullname).strip():
            return str(entry.fullname).strip(), containers
        first = (getattr(entry, "firstName", "") or "").strip()
        last = (getattr(entry, "lastName", "") or "").strip()
        combined = " ".join(x for x in [first, last] if x).strip()
        if combined:
            return combined, containers
    return None, containers


def _run_full_hunt(email: str) -> tuple[bool, str]:
    cmd = [sys.executable, str(Path(__file__).with_name("main.py")), "email", email.strip()]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "Full hunt timed out after 120s."

    output = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    if proc.returncode != 0:
        return False, "\n\n".join(x for x in [output, err] if x) or "Unknown CLI error."
    return True, output or "No output returned."


async def _lookup_display_name(
    email: str,
) -> tuple[bool, str | None, list[str], str | None, bool | None]:
    email = email.strip()
    ghunt_creds = GHuntCreds()
    ghunt_creds.load_creds()
    async with httpx.AsyncClient() as client:
        api = PeoplePaHttp(ghunt_creds)
        found, person = await api.people_lookup(
            client, email, params_template="just_name"
        )
        if not found:
            return False, None, [], None, None

        name, containers = _best_name_from_person(person)
        if name:
            return True, name, containers, None, None

        # Richer request — sometimes names only appear with max_details.
        try:
            found_md, person_md = await api.people_lookup(
                client, email, params_template="max_details"
            )
            if found_md:
                name, containers = _best_name_from_person(person_md)
                if name:
                    return True, name, containers, None, None
                person = person_md
        except Exception:
            pass

        # When Google withholds names, still provide actionable account status.
        gaia_id = None
        registered = None
        try:
            found_gaia, person_gaia = await api.people_lookup(
                client, email, params_template="just_gaia_id"
            )
            if found_gaia:
                gaia_id = person_gaia.personId
        except Exception:
            pass

        try:
            registered = await is_email_registered(client, email)
        except Exception:
            pass

        # Gaia proves a Google identity exists; don't treat as “unregistered”.
        if gaia_id:
            registered = True

        return True, None, containers, gaia_id, registered


async def _registration_status(email: str) -> tuple[bool | None, str]:
    email = email.strip()
    ghunt_creds = GHuntCreds()
    ghunt_creds.load_creds()

    async with httpx.AsyncClient() as client:
        # Fast probe first.
        try:
            if await is_email_registered(client, email):
                return True, "Confirmed by Gmail registration probe."
        except Exception:
            # Continue with fallback methods.
            pass

        # Fallback: if People lookup finds a Gaia profile, account exists.
        try:
            api = PeoplePaHttp(ghunt_creds)
            found_gaia, _ = await api.people_lookup(
                client, email, params_template="just_gaia_id"
            )
            if found_gaia:
                return True, "Confirmed by People lookup (Gaia profile found)."
        except Exception:
            pass

    return None, "Probe is inconclusive (Google may restrict this target)."


st.set_page_config(
    page_title="GHunt",
    page_icon="🔎",
    layout="centered",
)

st.title("GHunt")
st.caption("Use only on targets you are authorized to investigate.")

tab_name, tab_reg, tab_full, tab_about = st.tabs(
    ["Display name lookup", "Gmail / Google account?", "Full CLI hunt", "About"]
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
                    found, name, containers, gaia_id, registered = _run(
                        _lookup_display_name(email_a)
                    )
                except Exception as e:
                    st.error(f"Request failed: `{e}`")
                    st.info("Try `ghunt login` if credentials are missing or expired.")
                else:
                    if not found:
                        st.error("Not found via People lookup.")
                    elif name:
                        st.success(name)
                    else:
                        if containers:
                            st.warning(
                                "Found, but no display name was parsed from People data. "
                                f"Containers present: `{', '.join(containers)}`. "
                                "Try **Full CLI hunt** for the same depth as the terminal."
                            )
                        else:
                            st.info(
                                "Found account metadata, but no name fields were returned. "
                                "Use **Full CLI hunt** for services, maps, and calendar."
                            )

                        if gaia_id:
                            st.success("Google account confirmed (Gaia profile found).")
                            st.code(f"Gaia ID: {gaia_id}")
                        elif registered is True:
                            st.success("Google account appears registered (Gmail probe).")
                        else:
                            st.info(
                                "Could not confirm via People or Gmail probe — "
                                "try **Full CLI hunt** or re-run `ghunt login`."
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
                    reg, reason = _run(_registration_status(email_b))
                except Exception as e:
                    st.error(f"Request failed: `{e}`")
                else:
                    if reg is True:
                        st.success("Registered with Google.")
                    else:
                        st.info("Registration status is inconclusive.")
                    st.caption(reason)

with tab_full:
    st.markdown(
        "Run the full GHunt email module and display terminal-like results "
        "(services, maps, calendar, and more)."
    )
    email_full = st.text_input(
        "Email",
        key="full_email",
        placeholder="user@gmail.com",
    )
    if st.button("Run full GHunt hunt", key="btn_full"):
        if not email_full.strip():
            st.warning("Enter an email address.")
        else:
            with st.spinner("Running full GHunt CLI module..."):
                ok, output = _run_full_hunt(email_full)
            if ok:
                st.success("Full hunt completed.")
                st.code(output)
            else:
                st.error("Full hunt failed.")
                st.code(output)

with tab_about:
    st.markdown(
        """
        - **Full OSINT hunt** (maps, calendar, games, JSON export): use the CLI  
          `ghunt email <address> [--json out.json]`
        - **Auth**: `ghunt login`
        - Source examples: `examples/get_people_name.py`, `examples/email_registered.py`
        """
    )
