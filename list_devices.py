import pyaudiowpatch as pyaudio

with pyaudio.PyAudio() as p:
    wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    print(f"WASAPI host api index: {wasapi_info['index']}\n")

    print("=== Output devices (WASAPI) ===")
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        if d["hostApi"] == wasapi_info["index"] and d["maxOutputChannels"] > 0:
            print(f"[{d['index']}] {d['name']!r}  channels={d['maxOutputChannels']} rate={int(d['defaultSampleRate'])}")

    print("\n=== Loopback devices (what each output is currently playing) ===")
    for d in p.get_loopback_device_info_generator():
        print(f"[{d['index']}] {d['name']!r}  channels={d['maxInputChannels']} rate={int(d['defaultSampleRate'])}")
