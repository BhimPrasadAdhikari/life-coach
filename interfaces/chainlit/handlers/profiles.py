import chainlit as cl

PROFILE_MAP = {
    "GPT-OSS 120B (Groq — best)": "groq-llama3.3",
    "GPT-OSS 20B (Groq — fast)": "groq-llama3.1",
    "Qwen 3.8 27B (Groq — balanced)": "groq-qwen27b",
}

@cl.set_chat_profiles
async def set_chat_profiles(current_user: cl.User):
    return [
        cl.ChatProfile(name="GPT-OSS 120B (Groq — best)", markdown_description="**Groq — GPT-OSS 120B** (Default) High quality fast response via Groq."),
        cl.ChatProfile(name="GPT-OSS 20B (Groq — fast)", markdown_description="**Groq — GPT-OSS 20B** Ultra-fast lightweight model."),
        cl.ChatProfile(name="Qwen 3.8 27B (Groq — balanced)", markdown_description="**Groq — Qwen 3.8 27B** Balanced reasoning model."),
    ]