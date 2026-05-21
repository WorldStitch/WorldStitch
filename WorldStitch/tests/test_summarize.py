print("Importing Config...")
from WorldStitch.config.config import Config

print("Importing OpenaiAI...")
from WorldStitch.ai.core.openai_engine import OpenaiAI

print("Building config...")
config = Config()
print("Building AI backend...")
ai = OpenaiAI(config)
print("Ready to call summarize...")

test_text = "Write a summary of the history of the Forgotten Realms in D&D."
try:
    print("About to call summarize...")
    summary, prompt_tokens, resp_tokens = ai.summarize(test_text)
    print("SUMMARY:", summary)
    print("Prompt tokens:", prompt_tokens)
    print("Response tokens:", resp_tokens)
except Exception as e:
    print("ERROR:", e)
    import traceback

    traceback.print_exc()
print("Done with summarize test.")
