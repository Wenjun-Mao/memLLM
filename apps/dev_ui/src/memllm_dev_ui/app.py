from __future__ import annotations

import json

import httpx
import streamlit as st

from memllm_dev_ui.client import ApiClient
from memllm_dev_ui.settings import DevUiSettings


def _load_client() -> tuple[DevUiSettings, ApiClient]:
    settings = DevUiSettings()
    return settings, ApiClient(
        base_url=settings.api_base_url,
        timeout_seconds=settings.request_timeout_seconds,
    )


def _ensure_state() -> None:
    st.session_state.setdefault("messages", [])


def _render_memory(snapshot: dict) -> None:
    st.subheader("Memory Snapshot")
    if not snapshot:
        st.info("Seed a character and send a message to inspect memory.")
        return

    st.caption("Use Letta Desktop or ADE for direct memory editing. This panel is read-only.")
    blocks = snapshot.get("blocks", [])
    passages = snapshot.get("passages", [])
    with st.expander("Blocks", expanded=True):
        if not blocks:
            st.write("No blocks available.")
        for block in blocks:
            st.markdown(f"**{block['label']}**")
            st.code(block["value"])
    with st.expander("Passages", expanded=True):
        if not passages:
            st.write("No passages available.")
        for passage in passages:
            st.code(passage["text"])


def main() -> None:
    st.set_page_config(page_title="memLLM Dev UI", page_icon="🧠", layout="wide")
    _ensure_state()

    settings, client = _load_client()
    st.title("memLLM Phase 1 Dev UI")
    st.caption("Chat here. Inspect and edit detailed memory in Letta Desktop or the ADE.")

    with st.sidebar:
        st.header("Workspace")
        user_id = st.text_input("User ID", value=settings.default_user_id)
        seed_clicked = st.button("Seed Characters", use_container_width=True)
        st.markdown(
            "Use Letta Desktop in self-hosted server mode against the Docker Letta instance "
            "when you need direct memory inspection, editing, or debugging."
        )

    try:
        if seed_clicked:
            seed_report = client.seed_characters()
            st.sidebar.success(f"Seeded {len(seed_report.get('seeded', []))} characters.")
        characters = client.list_characters()
    except httpx.HTTPError as exc:
        st.error(f"API unavailable: {exc}")
        return

    if not characters:
        st.warning("No characters are seeded yet.")
        return

    character_map = {item["display_name"]: item for item in characters}
    selected_name = st.selectbox("Character", options=list(character_map))
    selected_character = character_map[selected_name]

    left, right = st.columns([1.7, 1.0])

    with left:
        st.subheader("Chat")
        for message in st.session_state["messages"]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        prompt = st.chat_input(f"Talk to {selected_character['display_name']}")
        if prompt:
            st.session_state["messages"].append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            try:
                response = client.send_chat(
                    user_id=user_id,
                    character_id=selected_character["character_id"],
                    message=prompt,
                )
            except httpx.HTTPStatusError as exc:
                st.error(f"Chat failed: {exc.response.text}")
                return
            except httpx.HTTPError as exc:
                st.error(f"Chat failed: {exc}")
                return

            reply = response["reply"]
            st.session_state["messages"].append({"role": "assistant", "content": reply})
            with st.chat_message("assistant"):
                st.markdown(reply)

    with right:
        st.subheader("Character")
        st.json(
            {
                "character_id": selected_character["character_id"],
                "description": selected_character["description"],
                "reply_provider": selected_character["reply_provider"],
            }
        )
        try:
            snapshot = client.get_memory(
                user_id=user_id, character_id=selected_character["character_id"]
            )
        except httpx.HTTPStatusError as exc:
            st.error(f"Memory load failed: {exc.response.text}")
            snapshot = {}
        except httpx.HTTPError as exc:
            st.error(f"Memory load failed: {exc}")
            snapshot = {}
        _render_memory(snapshot)

        with st.expander("Raw Snapshot"):
            st.code(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
