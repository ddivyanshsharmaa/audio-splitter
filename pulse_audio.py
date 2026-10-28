"""Linux routing through PulseAudio or PipeWire's PulseAudio server.

Own only the modules we load. Never change server config, start a server,
or unload somebody else's sink/loopbacks. pactl uses the user's local session.
"""
import json
import re
import subprocess


def pactl(*args, check=True):
    result = subprocess.run(["pactl", *map(str, args)], capture_output=True,
                            text=True, timeout=5)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or "pactl failed")
    return result.stdout.strip()


def listing(kind):
    return json.loads(pactl("--format=json", "list", kind))


def resolve(devices, name):
    """Prefer exact names; ambiguous fragments must never select a speaker."""
    exact = [d for d in devices if d["name"] == name]
    found = exact or [d for d in devices if name.casefold() in d["name"].casefold()]
    if len(found) != 1:
        raise RuntimeError(f"{name!r}: expected one device, found {len(found)}. "
                           "Run 'bash launch.sh list' and use an exact name.")
    return found[0]


class PulseAudio:
    # A server scheduling target, not a sample-accurate FIFO delay.
    BASE_LATENCY_MS = 10

    def __init__(self, sink_name):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", sink_name):
            raise ValueError("Linux VIRTUAL_SINK_NAME needs only letters, digits, _, . or -")
        self.sink_name = sink_name
        self.sink_module = None
        self.routes = {}
        self.previous = None
        self.moved = {}
        self.routed = False

    def outputs(self):
        return [{"name": d["name"], "label": d.get("description", d["name"]),
                 "is_sink": d["name"] == self.sink_name}
                for d in listing("sinks")]

    def _load(self, module, *args):
        value = pactl("load-module", module, *args)
        if not value.isdecimal():
            raise RuntimeError(f"No module ID returned for {module}: {value!r}")
        return value

    def start(self, outputs, delays):
        sinks = listing("sinks")
        if any(d["name"] == self.sink_name for d in sinks):
            raise RuntimeError(f"Sink {self.sink_name!r} already exists. Stop the other "
                               "splitter, or remove its stale modules (see README).")
        self.previous = pactl("get-default-sink")
        if not self.previous or self.previous == self.sink_name:
            raise RuntimeError("Select a real default output before starting.")
        # Resolve everything before creating or changing any routing.
        for out in outputs:
            resolve(sinks, out["name"])
        self.sink_module = self._load(
            "module-null-sink", f"sink_name={self.sink_name}",
            "rate=48000", "channels=2",
            "sink_properties=device.description=AudioSplitter")
        self.sync(outputs, delays)
        # The loopbacks are ready before applications are handed to the sink.
        self.routed = True
        pactl("set-default-sink", self.sink_name)
        self._move_existing(sinks)

    def _move_existing(self, sinks):
        by_index = {str(d["index"]): d["name"] for d in sinks}
        owned = {module for module, _ in self.routes.values()}
        for stream in listing("sink-inputs"):
            # Loopbacks already target real speakers. Moving one back to our
            # monitor sink would create a feedback loop and silence its speaker.
            if str(stream.get("owner_module")) in owned:
                continue
            original = by_index.get(str(stream["sink"]))
            if original == self.previous:
                index = str(stream["index"])
                self.moved[index] = original
                # Streams can finish between listing and moving.
                pactl("move-sink-input", index, self.sink_name, check=False)

    def sync(self, outputs, delays):
        wanted = {o["name"]: o for o in outputs}
        sinks = listing("sinks")
        resolved = {name: resolve(sinks, name) for name in wanted}
        if any(d["name"] == self.sink_name for d in resolved.values()):
            raise RuntimeError("The routing sink cannot be used as a speaker.")
        if len({d["name"] for d in resolved.values()}) != len(resolved):
            raise RuntimeError("Two configured names resolve to the same speaker.")
        for name in list(self.routes):
            target = self.BASE_LATENCY_MS + int(delays.get(name, 0))
            if name not in wanted or self.routes[name][1] != target:
                pactl("unload-module", self.routes[name][0])
                del self.routes[name]
        for name, out in wanted.items():
            if name not in self.routes:
                target = self.BASE_LATENCY_MS + int(delays.get(name, 0))
                module = self._load("module-loopback",
                                    f"source={self.sink_name}.monitor",
                                    f"sink={resolved[name]['name']}",
                                    f"latency_msec={target}",
                                    "source_dont_move=true", "sink_dont_move=true")
                self.routes[name] = (module, target)
        # Volume belongs to the loopback stream, leaving other apps' volume alone.
        owners = {str(s["owner_module"]): s["index"] for s in listing("sink-inputs")
                  if s.get("owner_module") is not None}
        for name, (module, _) in self.routes.items():
            if module in owners:
                volume = max(0, min(100, int(wanted[name].get("volume", 100))))
                pactl("set-sink-input-volume", owners[module], f"{volume}%")

    def stop(self):
        errors = []

        def attempt(*args):
            try:
                pactl(*args)
            except Exception as exc:
                errors.append(str(exc))

        if self.routed and self.previous:
            attempt("set-default-sink", self.previous)
            try:
                sinks = listing("sinks")
                sink = next((d for d in sinks if d["name"] == self.sink_name), None)
                if sink:
                    for stream in listing("sink-inputs"):
                        if str(stream["sink"]) == str(sink["index"]):
                            # Includes newly started apps, which weren't in moved.
                            destination = self.moved.get(str(stream["index"]), self.previous)
                            pactl("move-sink-input", stream["index"], destination, check=False)
            except Exception as exc:
                errors.append(str(exc))
        for module, _ in self.routes.values():
            attempt("unload-module", module)
        self.routes.clear()
        if self.sink_module is not None:
            attempt("unload-module", self.sink_module)
            self.sink_module = None
        self.routed = False
        if errors:
            raise RuntimeError("Routing cleanup: " + "; ".join(errors))
