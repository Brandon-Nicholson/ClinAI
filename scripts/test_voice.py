import asyncio
import edge_tts
import time
from app.voice.synthesizer import EdgeTTSPlayer

async def list_voices():
    voices = await edge_tts.list_voices()
    for v in voices:
        if "en-" in v["ShortName"]:   # just English ones
            print(f"{v['ShortName']} ({v['Locale']}): {v['Gender']} - {v['FriendlyName']}")

asyncio.run(list_voices())

tts = EdgeTTSPlayer(voice="en-US-AriaNeural", rate="+10%")
tts.speak("Hi. How can I assist you today?")
time.sleep(6)