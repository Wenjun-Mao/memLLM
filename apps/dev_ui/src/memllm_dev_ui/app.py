from __future__ import annotations

import json
from typing import Any

import httpx
import streamlit as st

from memllm_dev_ui.client import ApiClient
from memllm_dev_ui.settings import DevUiSettings

MEMORY_WORK_EVENT_ORDER = [
    'session_resolution',
    'memory_blocks_read',
    'archival_memory_search',
    'memory_extractor_call',
    'memory_block_update',
    'archival_memory_insert',
]


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


def _render_memory_blocks(memory_blocks: list[dict[str, Any]], *, empty_text: str) -> None:
    if not memory_blocks:
        st.write(empty_text)
        return
    for block in memory_blocks:
        label = block.get('label', 'unknown')
        scope = block.get('scope', 'unknown')
        st.markdown(f'**{label}**')
        st.caption(f'Scope: {scope}')
        if block.get('description'):
            st.caption(block['description'])
        st.code(block.get('value', ''))


def _render_archival_memory(archival_memory: list[dict[str, Any]], *, empty_text: str) -> None:
    if not archival_memory:
        st.write(empty_text)
        return
    for item in archival_memory:
        if item.get('score') is not None:
            st.caption(f"score={item['score']}")
        st.code(item.get('text', ''))


def _render_memory(snapshot: dict[str, Any]) -> None:
    st.subheader('Memory Snapshot')
    if not snapshot:
        st.info('Seed a character and send a message to inspect live Letta memory.')
        return

    st.caption(
        'Live Letta state for this user-agent pair. Memory Blocks approximate the working '
        'context; Archival Memory is the retrievable long-term store.'
    )
    st.caption('MemGPT paper mapping: Working Context + Archival Memory.')
    memory_blocks = snapshot.get('memory_blocks', [])
    archival_memory = snapshot.get('archival_memory', [])
    with st.expander('Memory Blocks', expanded=True):
        _render_memory_blocks(memory_blocks, empty_text='No memory blocks available.')
    with st.expander('Archival Memory', expanded=True):
        _render_archival_memory(
            archival_memory,
            empty_text='No archival memory items available.',
        )


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


def _render_prompt_pipeline(latest_debug: dict[str, Any]) -> None:
    st.subheader('Prompt Pipeline')
    st.caption(
        'This shows how the app assembled the final request: System Instructions, Working '
        'Context, Conversation Window, and retrieved Archival Memory.'
    )
    st.caption('MemGPT paper mapping: System Instructions + Working Context + FIFO Queue analogue.')
    pipeline = latest_debug.get('prompt_pipeline') if latest_debug else None
    if not pipeline:
        st.info('Send a message to inspect the prompt assembly for the current round.')
        return

    with st.expander('System Instructions', expanded=True):
        st.code(pipeline.get('system_instructions', ''))
    with st.expander('Working Context', expanded=True):
        working_context = pipeline.get('working_context', {})
        st.caption('Shared memory blocks')
        _render_memory_blocks(
            working_context.get('shared_memory_blocks', []),
            empty_text='No shared memory blocks in working context.',
        )
        st.caption('User memory blocks')
        _render_memory_blocks(
            working_context.get('user_memory_blocks', []),
            empty_text='No user memory blocks in working context.',
        )
    with st.expander('Conversation Window', expanded=False):
        conversation_window = pipeline.get('conversation_window', [])
        if not conversation_window:
            st.write('No conversation window available.')
        for message in conversation_window:
            st.markdown(f"**{message.get('role', 'unknown')}**")
            st.code(message.get('content', ''))
    with st.expander('Retrieved Archival Memory', expanded=False):
        _render_archival_memory(
            pipeline.get('retrieved_archival_memory', []),
            empty_text='No archival memory was retrieved for this round.',
        )
    with st.expander('Final Provider Payload', expanded=False):
        _render_jsonish(pipeline.get('final_provider_payload'))


def _ordered_memory_work_events(trace_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranking = {kind: index for index, kind in enumerate(MEMORY_WORK_EVENT_ORDER)}
    return sorted(
        [event for event in trace_events if event.get('kind') in ranking],
        key=lambda item: ranking[item.get('kind', '')],
    )


def _render_trace_event(event: dict[str, Any], *, expanded: bool) -> None:
    title = event.get('title', event.get('kind', 'Event'))
    with st.expander(title, expanded=expanded):
        if event.get('description'):
            st.caption(event['description'])
        if event.get('paper_mapping'):
            st.caption(f"Paper mapping: {event['paper_mapping']}")
        st.caption('Request')
        _render_jsonish(event.get('request'))
        st.caption('Response')
        _render_jsonish(event.get('response'))


def _render_current_round_memory_work(latest_debug: dict[str, Any]) -> None:
    st.subheader('Current-Round Memory Work')
    st.caption(
        'This is the live trace for the current round: Letta reads/searches, the local '
        'memory extractor call, and the Letta write operations.'
    )
    st.caption('MemGPT paper mapping: Working Context updates and Archival Memory writes.')
    if not latest_debug:
        st.info('Send a message to inspect the current round trace.')
        return

    trace_events = latest_debug.get('trace_events', [])
    memory_events = _ordered_memory_work_events(trace_events)
    if not memory_events:
        st.info('No current-round memory work is available yet.')
    else:
        for index, event in enumerate(memory_events):
            _render_trace_event(event, expanded=index == len(memory_events) - 1)

    with st.expander('Writeback Summary', expanded=False):
        memory_writeback = latest_debug.get('memory_writeback')
        if not memory_writeback:
            st.write('No inline writeback data is available for this round.')
        else:
            _render_jsonish(memory_writeback)

    with st.expander('Full Current-Round Trace', expanded=False):
        for event in trace_events:
            _render_trace_event(event, expanded=False)


def _render_final_provider_call(latest_debug: dict[str, Any]) -> None:
    st.subheader('Final Provider Call')
    st.caption(
        'This is the exact last outbound request sent to the final reply provider after '
        'prompt assembly.'
    )
    final_provider_call = latest_debug.get('final_provider_call') if latest_debug else None
    if not final_provider_call:
        st.info('Send a message to inspect the final outbound provider request for this round.')
        return
    _render_jsonish(final_provider_call)


def _render_debug_history(debug_turns: list[dict[str, Any]]) -> None:
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
            format_func=lambda idx: f"Round {idx + 1}: {debug_turns[idx]['user_message'][:48]}",
        )
        chosen = debug_turns[selected]
        st.caption('Latest browser-session snapshot for that round')
        _render_jsonish(chosen)


def main() -> None:
    st.set_page_config(page_title='memLLM Dev UI', page_icon='🧠', layout='wide')
    _ensure_state()

    settings, client = _load_client()
    st.title('memLLM Phase 1 Dev UI')
    st.caption('Chat here. Inspect and explain the Letta-backed memory flow round by round.')
    with st.expander('How to Read This Page', expanded=False):
        st.markdown(
            """
- `Chat`: the user-visible conversation only.
- `User-Agent Pair`: the Letta agent that stores memory for one user talking to one character.
- `Final Provider Call`: the exact last request that went to DouBao or local Ollama.
- `Prompt Pipeline`: the assembled System Instructions, Working Context,
  Conversation Window, and retrieved Archival Memory.
- `Current-Round Memory Work`: the live trace for Letta reads/searches,
  local memory extraction, and Letta writes.
- `Memory Snapshot`: the current live Letta state for this pair.
"""
        )

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

    left, right = st.columns([0.9, 1.45], gap='large')

    with left:
        st.subheader('Chat')
        st.caption(
            'This is only the user-facing conversation. Prompt assembly and memory work are '
            'shown separately on the right.'
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
                        'debug': response.get('debug') or {},
                    }
                )
                st.markdown(reply)
            st.rerun()

    latest_debug = conversation['debug_turns'][-1]['debug'] if conversation['debug_turns'] else {}

    with right:
        st.subheader('Character')
        st.caption(
            'This is the repo-defined character manifest, not live memory. It controls '
            'System Instructions, provider settings, seeded memory blocks, and archival seed text.'
        )
        st.json(
            {
                'character_id': selected_character['character_id'],
                'description': selected_character['description'],
                'reply_provider': selected_character['reply_provider'],
                'memory': selected_character['memory'],
            }
        )
        _render_session_manager(
            client=client,
            sessions=sessions,
            user_id=user_id,
            character=selected_character,
        )
        _render_final_provider_call(latest_debug)
        _render_prompt_pipeline(latest_debug)
        _render_current_round_memory_work(latest_debug)
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
        _render_debug_history(conversation['debug_turns'])

        with st.expander('Raw Snapshot', expanded=False):
            st.caption('Low-level JSON view of the current live memory snapshot.')
            st.code(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
