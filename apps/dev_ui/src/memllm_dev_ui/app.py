from __future__ import annotations

import json
from typing import Any

import httpx
import streamlit as st

from memllm_dev_ui.client import ApiClient
from memllm_dev_ui.settings import DevUiSettings

STEP_METADATA = {
    'session_resolution': {
        'title': 'Session Resolution',
        'description': (
            'Resolve or create the Letta agent for this specific user and character pair.'
        ),
    },
    'letta_memory_context': {
        'title': 'Letta Memory Retrieval',
        'description': (
            'Fetch the memory Letta returns for this turn: shared character blocks, '
            'user-specific blocks, and retrieved passages.'
        ),
    },
    'message_history': {
        'title': 'Message History Selection',
        'description': (
            'Select the recent conversation window that will be included in the final '
            'reply request.'
        ),
    },
    'reply_provider_resolution': {
        'title': 'Reply Provider Resolution',
        'description': (
            'Choose the adapter and runtime settings for the user-facing reply provider.'
        ),
    },
    'memory_persistence_schedule': {
        'title': 'Memory Persistence Scheduling',
        'description': (
            'Queue the local memory extraction and Letta write-back that happen after '
            'the user-facing reply is generated.'
        ),
    },
}


def _load_client() -> tuple[DevUiSettings, ApiClient]:
    settings = DevUiSettings()
    return settings, ApiClient(
        base_url=settings.api_base_url,
        timeout_seconds=settings.request_timeout_seconds,
    )


def _ensure_state() -> None:
    st.session_state.setdefault('conversations', {})


def _conversation_key(*, user_id: str, character_id: str) -> str:
    return f'{user_id}::{character_id}'


def _conversation_state(*, user_id: str, character_id: str) -> dict[str, list[dict[str, Any]]]:
    key = _conversation_key(user_id=user_id, character_id=character_id)
    conversations = st.session_state['conversations']
    if key not in conversations:
        conversations[key] = {'messages': [], 'debug_turns': []}
    return conversations[key]


def _drop_conversation_state(*, user_id: str, character_id: str) -> None:
    key = _conversation_key(user_id=user_id, character_id=character_id)
    st.session_state['conversations'].pop(key, None)


def _render_jsonish(value: Any, *, fallback_label: str = 'Value') -> None:
    if value is None:
        st.caption('None')
        return
    if isinstance(value, (dict, list)):
        st.json(value)
        return
    st.caption(fallback_label)
    st.code(str(value))


def _render_memory(snapshot: dict[str, Any]) -> None:
    st.subheader('Memory Snapshot')
    if not snapshot:
        st.info('Seed a character and send a message to inspect memory.')
        return

    st.caption(
        'This is the current Letta-backed memory view for the selected user and '
        'character: shared character memory plus user-specific memory and retrieved '
        'passages. Use Letta Desktop or ADE for direct editing.'
    )
    blocks = snapshot.get('blocks', [])
    passages = snapshot.get('passages', [])
    with st.expander('Blocks', expanded=True):
        if not blocks:
            st.write('No blocks available.')
        for block in blocks:
            st.markdown(f"**{block['label']}**")
            st.code(block['value'])
    with st.expander('Passages', expanded=True):
        if not passages:
            st.write('No passages available.')
        for passage in passages:
            st.code(passage['text'])


def _render_session_manager(
    *,
    client: ApiClient,
    sessions: list[dict[str, Any]],
    user_id: str,
    character: dict[str, Any],
) -> None:
    st.subheader('User-Agent Pair')
    st.caption(
        'Each user and character combination gets its own Letta agent, so memory stays '
        'isolated per pair.'
    )
    current_session = next(
        (
            session
            for session in sessions
            if session['user_id'] == user_id
            and session['character_id'] == character['character_id']
        ),
        None,
    )
    if current_session:
        st.json(current_session)
    else:
        st.info('No Letta session exists yet for this user/character pair.')

    if st.button(
        'Delete Current Pair',
        use_container_width=True,
        disabled=current_session is None,
    ):
        client.delete_session(user_id=user_id, character_id=character['character_id'])
        _drop_conversation_state(user_id=user_id, character_id=character['character_id'])
        st.rerun()

    with st.expander('All User-Agent Pairs', expanded=False):
        if not sessions:
            st.write('No user-agent pairs exist yet.')
            return
        for session in sessions:
            is_current = (
                session['user_id'] == user_id
                and session['character_id'] == character['character_id']
            )
            label = (
                f"{session['user_id']} -> {session['character_display_name']} "
                f"({session['character_id']})"
            )
            if is_current:
                label = f'{label} [current]'
            cols = st.columns([4, 1])
            cols[0].markdown(f'**{label}**')
            cols[0].caption(session['agent_id'])
            if cols[1].button(
                'Delete',
                key=f"delete-session-{session['user_id']}-{session['character_id']}",
                use_container_width=True,
            ):
                client.delete_session(
                    user_id=session['user_id'],
                    character_id=session['character_id'],
                )
                _drop_conversation_state(
                    user_id=session['user_id'],
                    character_id=session['character_id'],
                )
                st.rerun()


def _render_debug_panels(debug_turns: list[dict[str, Any]]) -> None:
    latest = debug_turns[-1] if debug_turns else None
    final_request = (latest or {}).get('debug', {}).get('final_request')
    steps = (latest or {}).get('debug', {}).get('steps', [])

    st.subheader('Final Provider Call')
    st.caption(
        'This is the exact last outbound request sent to the final reply provider for '
        'this round, after memory retrieval and request assembly.'
    )
    if not final_request:
        st.info('Send a message to inspect the final outbound provider request for this round.')
    else:
        _render_jsonish(final_request)

    st.subheader('Middle Steps')
    st.caption(
        'These are the in-process orchestration steps for the current round. They show '
        'how memory was loaded and how the final reply call was prepared.'
    )
    if not steps:
        st.info('No middle-step trace is available for this round yet.')
    else:
        for index, step in enumerate(steps, start=1):
            metadata = STEP_METADATA.get(step['label'], {})
            title = metadata.get('title', step['label'].replace('_', ' ').title())
            with st.expander(f'{index}. {title}', expanded=index == len(steps)):
                description = metadata.get('description')
                if description:
                    st.caption(description)
                st.caption('Input')
                _render_jsonish(step.get('input'))
                st.caption('Output')
                _render_jsonish(step.get('output'))

    with st.expander('Debug History', expanded=False):
        st.caption(
            'Browser-session-only snapshots of earlier rounds. This does not persist to '
            'Letta or the app database.'
        )
        if not debug_turns:
            st.write('No previous debug rounds in this browser session.')
            return
        options = list(range(len(debug_turns) - 1, -1, -1))
        selected = st.selectbox(
            'Round',
            options=options,
            format_func=lambda idx: (
                f"Round {idx + 1}: {debug_turns[idx]['user_message'][:48]}"
            ),
        )
        chosen = debug_turns[selected]
        st.caption('Latest browser-session snapshot for that round')
        _render_jsonish(chosen)


def main() -> None:
    st.set_page_config(page_title='memLLM Dev UI', page_icon='🧠', layout='wide')
    _ensure_state()

    settings, client = _load_client()
    st.title('memLLM Phase 1 Dev UI')
    st.caption(
        'Chat here. Inspect and edit detailed memory in Letta Desktop or the ADE.'
    )
    with st.expander('How to Read This Page', expanded=False):
        st.markdown("""
- `Chat`: the user-visible conversation.
- `Character`: the repo-defined manifest and reply-provider configuration.
- `User-Agent Pair`: the Letta agent that stores memory for one user talking to one character.
- `Final Provider Call`: the exact last payload sent to DouBao or local Ollama.
- `Middle Steps`: the temporary orchestration trace for this round only.
- `Memory Snapshot`: the current Letta-backed memory state for this pair.
""")

    with st.sidebar:
        st.header('Workspace')
        user_id = st.text_input('User ID', value=settings.default_user_id)
        seed_clicked = st.button('Seed Characters', use_container_width=True)
        st.caption(
            'Request timeout: '
            f'{settings.request_timeout_seconds:.0f}s. '
            'Cold model loads can take longer on smaller GPUs.'
        )
        st.markdown(
            'Use Letta Desktop in self-hosted server mode against the Docker Letta instance '
            'when you need direct memory inspection, editing, or debugging.'
        )

    try:
        if seed_clicked:
            seed_report = client.seed_characters()
            st.sidebar.success(f"Seeded {len(seed_report.get('seeded', []))} characters.")
        characters = client.list_characters()
        sessions = client.list_sessions()
    except httpx.HTTPError as exc:
        st.error(f'API unavailable: {exc}')
        return

    if not characters:
        st.warning('No characters are seeded yet.')
        return

    character_map = {item['display_name']: item for item in characters}
    selected_name = st.selectbox('Character', options=list(character_map))
    selected_character = character_map[selected_name]
    conversation = _conversation_state(
        user_id=user_id,
        character_id=selected_character['character_id'],
    )

    left, right = st.columns([1.05, 1.25], gap='large')

    with left:
        st.subheader('Chat')
        st.caption(
            'This is the user-facing conversation only. Memory retrieval and provider '
            'calls are shown separately on the right.'
        )
        for message in conversation['messages']:
            with st.chat_message(message['role']):
                st.markdown(message['content'])

        prompt = st.chat_input(f"Talk to {selected_character['display_name']}")
        if prompt:
            conversation['messages'].append({'role': 'user', 'content': prompt})
            with st.chat_message('user'):
                st.markdown(prompt)
            with st.chat_message('assistant'):
                with st.spinner('Generating reply. Cold starts can take a while on smaller GPUs.'):
                    try:
                        response = client.send_chat(
                            user_id=user_id,
                            character_id=selected_character['character_id'],
                            message=prompt,
                        )
                    except httpx.HTTPStatusError as exc:
                        st.error(f'Chat failed: {exc.response.text}')
                        return
                    except httpx.HTTPError as exc:
                        st.error(f'Chat failed: {exc}')
                        return

                reply = response['reply']
                conversation['messages'].append({'role': 'assistant', 'content': reply})
                conversation['debug_turns'].append(
                    {
                        'user_message': prompt,
                        'assistant_message': reply,
                        'debug': response.get('debug'),
                    }
                )
                st.markdown(reply)
            st.rerun()

    with right:
        st.subheader('Character')
        st.caption(
            'This is the repo-defined character manifest, not live memory. It controls the '
            'persona, provider, and memory defaults.'
        )
        st.json(
            {
                'character_id': selected_character['character_id'],
                'description': selected_character['description'],
                'reply_provider': selected_character['reply_provider'],
            }
        )
        _render_session_manager(
            client=client,
            sessions=sessions,
            user_id=user_id,
            character=selected_character,
        )
        _render_debug_panels(conversation['debug_turns'])
        try:
            snapshot = client.get_memory(
                user_id=user_id,
                character_id=selected_character['character_id'],
            )
        except httpx.HTTPStatusError as exc:
            st.error(f'Memory load failed: {exc.response.text}')
            snapshot = {}
        except httpx.HTTPError as exc:
            st.error(f'Memory load failed: {exc}')
            snapshot = {}
        _render_memory(snapshot)

        with st.expander('Raw Snapshot'):
            st.caption('Low-level JSON view of the current memory snapshot.')
            st.code(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
