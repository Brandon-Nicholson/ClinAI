import asyncio
import edge_tts

async def list_voices():
    voices = await edge_tts.list_voices()
    for v in voices:
        if "en-" in v["ShortName"]:   # just English ones
            print(f"{v['ShortName']} ({v['Locale']}): {v['Gender']} - {v['FriendlyName']}")

asyncio.run(list_voices())

from synthesizer import EdgeTTSPlayer
import time


tts = EdgeTTSPlayer(voice="en-US-AvaMultilingualNeural", rate="+10%")
tts.speak("Hey")
time.sleep(10)

"""
en-AU-WilliamMultilingualNeural (en-AU): Male - Microsoft WilliamMultilingual Online (Natural) - English (Australia)
en-AU-NatashaNeural (en-AU): Female - Microsoft Natasha Online (Natural) - English (Australia)
en-CA-ClaraNeural (en-CA): Female - Microsoft Clara Online (Natural) - English (Canada)
en-CA-LiamNeural (en-CA): Male - Microsoft Liam Online (Natural) - English (Canada)
en-HK-YanNeural (en-HK): Female - Microsoft Yan Online (Natural) - English (Hong Kong SAR)
en-HK-SamNeural (en-HK): Male - Microsoft Sam Online (Natural) - English (Hongkong)
en-IN-NeerjaExpressiveNeural (en-IN): Female - Microsoft Neerja Online (Natural) - English (India) (Preview)
en-IN-NeerjaNeural (en-IN): Female - Microsoft Neerja Online (Natural) - English (India)
en-IN-PrabhatNeural (en-IN): Male - Microsoft Prabhat Online (Natural) - English (India)
en-IE-ConnorNeural (en-IE): Male - Microsoft Connor Online (Natural) - English (Ireland)
en-IE-EmilyNeural (en-IE): Female - Microsoft Emily Online (Natural) - English (Ireland)
en-KE-AsiliaNeural (en-KE): Female - Microsoft Asilia Online (Natural) - English (Kenya)
en-KE-ChilembaNeural (en-KE): Male - Microsoft Chilemba Online (Natural) - English (Kenya)
en-NZ-MitchellNeural (en-NZ): Male - Microsoft Mitchell Online (Natural) - English (New Zealand)
en-NZ-MollyNeural (en-NZ): Female - Microsoft Molly Online (Natural) - English (New Zealand)
en-NG-AbeoNeural (en-NG): Male - Microsoft Abeo Online (Natural) - English (Nigeria)
en-NG-EzinneNeural (en-NG): Female - Microsoft Ezinne Online (Natural) - English (Nigeria)
en-PH-JamesNeural (en-PH): Male - Microsoft James Online (Natural) - English (Philippines)
en-PH-RosaNeural (en-PH): Female - Microsoft Rosa Online (Natural) - English (Philippines)
en-US-AvaNeural (en-US): Female - Microsoft Ava Online (Natural) - English (United States)
en-US-AndrewNeural (en-US): Male - Microsoft Andrew Online (Natural) - English (United States)
en-US-EmmaNeural (en-US): Female - Microsoft Emma Online (Natural) - English (United States)
en-US-BrianNeural (en-US): Male - Microsoft Brian Online (Natural) - English (United States)
en-SG-LunaNeural (en-SG): Female - Microsoft Luna Online (Natural) - English (Singapore)
en-SG-WayneNeural (en-SG): Male - Microsoft Wayne Online (Natural) - English (Singapore)
en-ZA-LeahNeural (en-ZA): Female - Microsoft Leah Online (Natural) - English (South Africa)
en-ZA-LukeNeural (en-ZA): Male - Microsoft Luke Online (Natural) - English (South Africa)
en-TZ-ElimuNeural (en-TZ): Male - Microsoft Elimu Online (Natural) - English (Tanzania)
en-TZ-ImaniNeural (en-TZ): Female - Microsoft Imani Online (Natural) - English (Tanzania)
en-GB-LibbyNeural (en-GB): Female - Microsoft Libby Online (Natural) - English (United Kingdom)
en-GB-MaisieNeural (en-GB): Female - Microsoft Maisie Online (Natural) - English (United Kingdom)
en-GB-RyanNeural (en-GB): Male - Microsoft Ryan Online (Natural) - English (United Kingdom)
en-GB-SoniaNeural (en-GB): Female - Microsoft Sonia Online (Natural) - English (United Kingdom)
en-GB-ThomasNeural (en-GB): Male - Microsoft Thomas Online (Natural) - English (United Kingdom)
en-US-AnaNeural (en-US): Female - Microsoft Ana Online (Natural) - English (United States)
en-US-AndrewMultilingualNeural (en-US): Male - Microsoft AndrewMultilingual Online (Natural) - English (United States)
en-US-AriaNeural (en-US): Female - Microsoft Aria Online (Natural) - English (United States)
en-US-AvaMultilingualNeural (en-US): Female - Microsoft AvaMultilingual Online (Natural) - English (United States)
en-US-BrianMultilingualNeural (en-US): Male - Microsoft BrianMultilingual Online (Natural) - English (United States)
en-US-ChristopherNeural (en-US): Male - Microsoft Christopher Online (Natural) - English (United States)
en-US-EmmaMultilingualNeural (en-US): Female - Microsoft EmmaMultilingual Online (Natural) - English (United States)
en-US-EricNeural (en-US): Male - Microsoft Eric Online (Natural) - English (United States)
en-US-GuyNeural (en-US): Male - Microsoft Guy Online (Natural) - English (United States)
en-US-JennyNeural (en-US): Female - Microsoft Jenny Online (Natural) - English (United States)
en-US-MichelleNeural (en-US): Female - Microsoft Michelle Online (Natural) - English (United States)
en-US-RogerNeural (en-US): Male - Microsoft Roger Online (Natural) - English (United States)
en-US-SteffanNeural (en-US): Male - Microsoft Steffan Online (Natural) - English (United States)
"""

