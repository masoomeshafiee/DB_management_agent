from google.adk.models.google_llm import Gemini
from google.genai import types

summerizer_model = Gemini(model_name="gemini-2.5-flash-lite")

async def compress_history_if_needed(runner, threshold: int = 15):
    """
    Compresses the conversation history if it exceeds the specified threshold.
    Args:
        runner: The InMemoryRunner instance managing the conversation.
        threshold: The number of turns after which compression is triggered.
    """

    history = getattr(runner, 'history', [])

    if len(history) <= threshold:
        return
    
    print("Consolidationg history to reduce token usage...")
    system_instruction = history[0]
    recent_history = history[-10:]
    to_summerize = history[1:-10]

    text_log = "\n".join([f"{msg.role}: {''.join([part.text for part in msg.content.parts if part.text])}" for msg in to_summerize])

    prompt = f"""
        Summerize this data management conversation between a user and an AI assistant. 
        Keep experiment names, active SQL filters, and any important decisions made.
        Be concise but retain all critical information that may be needed later. 
        LOG:
        {text_log}
        SUMMARIZE:
    """
    response = await summerizer_model.generate_message(prompt=prompt)

    summary_msg = types.Content(
        role="system",
        parts=[types.Part(text=f"Conversation Summary: {response.text}")])
    
    runner.history = [system_instruction, summary_msg] + recent_history
    print("History consolidation complete.")
    