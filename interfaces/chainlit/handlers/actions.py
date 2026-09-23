import uuid
import chainlit as cl

@cl.action_callback("approve_skill")
async def approve_skill_action(action: cl.Action):
    skill_id = (action.payload or {}).get("skill_id")
    if not skill_id:
        await cl.Message(content="No skill_id provided for approval.").send()
        return
    try:
        from modules.self_evolution.skill_manager import get_skill_manager
        sm = get_skill_manager()
        skill = sm.approve_skill(skill_id)
        await cl.Message(content=f"✅ Approved skill: **{skill['name']}**").send()
        await cl.Message(content=sm.get_skill_summary(), author="Marcus").send()
    except Exception as e:
        await cl.Message(content=f"Error approving skill: {e}").send()

@cl.action_callback("new_conversation")
async def new_conversation_callback(action: cl.Action):
    cl.user_session.set("thread_id", str(uuid.uuid4()))
    actions = [cl.Action(name="new_conversation", label="🆕 New Conversation", payload={})]
    await cl.Message(content="Fresh start. What do you want to work on?", actions=actions, author="Marcus").send()