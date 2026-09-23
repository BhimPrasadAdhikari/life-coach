import chainlit as cl

@cl.password_auth_callback
def auth_callback(username: str, password: str):
    return cl.User(identifier=username, metadata={"role": "user", "provider": "dev-mode"})