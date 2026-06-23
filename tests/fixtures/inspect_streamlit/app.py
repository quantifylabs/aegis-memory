"""Faithful replica of the mem0-memory-agent cold-test target (Streamlit + Mem0).

The poisoning flow: raw user input from ``st.chat_input`` (captured via a walrus) is written
straight into Mem0 memory. The analyzer must (1) resolve the source to ``chat_input``,
(2) escalate the write, (3) emit the tailored ``guard.write(...)`` fix with the sink arg replaced
by ``verdict.content``, and (4) label the sink ``mem0`` (file imports ``mem0``).
"""

import streamlit as st
from mem0 import Memory


def main():
    memory = Memory()
    st.session_state.memory = memory

    if prompt := st.chat_input("What is up?"):
        # Untrusted user input written straight to memory (the poisoning flow).
        st.session_state.memory.add(messages=prompt, user_id="customer_service_bot")
