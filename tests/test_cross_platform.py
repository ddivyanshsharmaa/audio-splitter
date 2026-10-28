"""Run with standard Python; optional dependency tests skip when unavailable.

No audio is routed and no personal config.py is needed. Install the platform's
requirements to run the NumPy/psutil tests too; sounddevice is always mocked.
"""
import importlib.util
import json
from pathlib import Path
import runpy
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def optional_import(name):
    try:
        return __import__(name)
    except ModuleNotFoundError as exc:
        if exc.name != name and not (name == "tkinter" and exc.name == "_tkinter"):
            raise  # An installed but broken dependency is a real failure.
        return None


np = optional_import("numpy")
psutil = optional_import("psutil")
tkinter = optional_import("tkinter")

from coreaudio import Address, fourcc
from pulse_audio import PulseAudio, resolve
import unix_audio
if np is not None:
    from mac_audio import DelayBuffer, MacAudio, stereo_channels
    from resampler import Resampler
if psutil is not None:
    import unix_control


class FakePulse:
    def __init__(self):
        self.sinks = [{"name": "wired", "description": "Wired", "index": 1},
                      {"name": "bluetooth", "index": 2}]
        self.streams = [{"index": 10, "sink": 1, "owner_module": None},
                        {"index": 11, "sink": 2, "owner_module": None}]
        self.default = "wired"
        self.modules = {"99": "unrelated"}
        self.calls = []
        self.next_id = 100
        self.fail_route = None

    def listing(self, kind):
        return [dict(d) for d in (self.sinks if kind == "sinks" else self.streams)]

    def __call__(self, *args, check=True):
        args = tuple(map(str, args))
        self.calls.append(args)
        command = args[0]
        if command == "get-default-sink":
            return self.default
        if command == "load-module":
            if self.fail_route and f"sink={self.fail_route}" in args:
                raise RuntimeError("unavailable output")
            module = str(self.next_id)
            self.next_id += 1
            self.modules[module] = args[1]
            if args[1] == "module-null-sink":
                self.sinks.append({"name": "audio_splitter", "index": 3})
            else:
                name = next(a[5:] for a in args if a.startswith("sink="))
                sink = next(s for s in self.sinks if s["name"] == name)
                self.streams.append({"index": int(module), "sink": sink["index"],
                                     "owner_module": int(module)})
            return module
        if command == "unload-module":
            self.modules.pop(args[1])
            self.streams = [s for s in self.streams if str(s["owner_module"]) != args[1]]
            if args[1] == "100":
                self.sinks = [s for s in self.sinks if s["index"] != 3]
        elif command == "set-default-sink":
            self.default = args[1]
        elif command == "move-sink-input":
            stream = next(s for s in self.streams if str(s["index"]) == args[1])
            stream["sink"] = next(s["index"] for s in self.sinks if s["name"] == args[2])
        elif command != "set-sink-input-volume":
            raise AssertionError(args)
        return ""


OUTPUTS = [{"name": "wired", "volume": 70}, {"name": "bluetooth", "volume": 40}]
DELAYS = {"wired": 200, "bluetooth": 0}


class PulseTests(unittest.TestCase):
    def setUp(self):
        self.server = FakePulse()
        self.patches = [patch("pulse_audio.pactl", self.server),
                        patch("pulse_audio.listing", self.server.listing)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.audio = PulseAudio("audio_splitter")

    def test_routing_existing_and_new_streams_and_restoration(self):
        self.audio.start(OUTPUTS, DELAYS)
        self.assertEqual(self.server.default, "audio_splitter")
        self.assertEqual(self.server.streams[0]["sink"], 3)
        self.assertEqual(self.server.streams[1]["sink"], 2)  # pinned elsewhere
        self.assertIn(("set-sink-input-volume", "101", "70%"), self.server.calls)
        self.assertTrue(any("latency_msec=210" in c for c in self.server.calls))
        self.assertEqual([s["sink"] for s in self.server.streams[2:]], [1, 2])
        self.assertFalse(any(c[0] == "move-sink-input" and c[1] in ("101", "102")
                             for c in self.server.calls))
        self.server.streams.append({"index": 12, "sink": 3, "owner_module": None})
        self.audio.stop()
        self.assertEqual(self.server.default, "wired")
        self.assertEqual([s["sink"] for s in self.server.streams], [1, 2, 1])
        self.assertEqual(self.server.modules, {"99": "unrelated"})

    def test_latency_replaces_only_changed_route_volume_does_not(self):
        self.audio.start(OUTPUTS, DELAYS)
        bt_module = self.audio.routes["bluetooth"][0]
        wired_module = self.audio.routes["wired"][0]
        self.audio.sync(OUTPUTS, {"wired": 100, "bluetooth": 0})
        self.assertNotEqual(wired_module, self.audio.routes["wired"][0])
        self.assertEqual(bt_module, self.audio.routes["bluetooth"][0])
        before = dict(self.audio.routes)
        self.audio.sync([dict(o, volume=20) for o in OUTPUTS], {"wired": 100})
        self.assertEqual(before, self.audio.routes)
        self.audio.stop()

    def test_partial_start_is_cleaned_up_without_changing_default(self):
        self.server.fail_route = "bluetooth"
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            self.audio.start(OUTPUTS, DELAYS)
        self.audio.stop()
        self.assertEqual(self.server.default, "wired")
        self.assertEqual(self.server.modules, {"99": "unrelated"})

    def test_failure_after_default_switch_restores_apps_and_unloads_modules(self):
        with patch.object(self.audio, "_move_existing", side_effect=RuntimeError("move failed")):
            with self.assertRaisesRegex(RuntimeError, "move failed"):
                self.audio.start(OUTPUTS, DELAYS)
        self.assertEqual(self.server.default, "audio_splitter")
        self.audio.stop()
        self.assertEqual(self.server.default, "wired")
        self.assertEqual(self.server.modules, {"99": "unrelated"})

    def test_existing_virtual_sink_is_never_claimed_or_removed(self):
        self.server.sinks.append({"name": "audio_splitter", "index": 3})
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            self.audio.start(OUTPUTS, DELAYS)
        self.audio.stop()
        self.assertFalse(any(c[0] == "unload-module" for c in self.server.calls))

    def test_feedback_and_duplicate_aliases_are_rejected(self):
        self.audio.start(OUTPUTS, DELAYS)
        for outputs in ([{"name": "audio_splitter"}], [{"name": "wired"}, {"name": "wire"}]):
            with self.assertRaises(RuntimeError):
                self.audio.sync(outputs, {})
        self.audio.stop()

    def test_ambiguous_missing_and_exact_names(self):
        devices = [{"name": "USB"}, {"name": "USB headphones"}]
        self.assertEqual(resolve(devices, "USB")["name"], "USB")
        for name in ("head", "missing"):
            if name == "head":
                self.assertEqual(resolve(devices, name)["name"], "USB headphones")
            else:
                with self.assertRaises(RuntimeError):
                    resolve(devices, name)
        with self.assertRaises(RuntimeError):
            resolve(devices, "U")


class CoreAudioTests(unittest.TestCase):
    def test_coreaudio_constants_and_structure(self):
        import ctypes
        self.assertEqual(fourcc("dOut"), 0x644F7574)
        self.assertEqual(fourcc("dev#"), 0x64657623)
        self.assertEqual(ctypes.sizeof(Address), 12)
        self.assertEqual(Address(fourcc("dOut"), fourcc("glob"), 0).element, 0)


@unittest.skipIf(np is None, "NumPy is optional; install requirements to run DSP tests")
class DSPTests(unittest.TestCase):
    def test_live_delay_growth_shrink_and_zero(self):
        buffer = DelayBuffer()
        chunk = lambda n: np.full((480, 2), n, dtype=np.float32)
        np.testing.assert_array_equal(buffer.process(chunk(1), 2), chunk(0))
        np.testing.assert_array_equal(buffer.process(chunk(2), 2), chunk(0))
        np.testing.assert_array_equal(buffer.process(chunk(3), 2), chunk(1))
        np.testing.assert_array_equal(buffer.process(chunk(4), 1), chunk(3))
        np.testing.assert_array_equal(buffer.process(chunk(5), 0), chunk(5))
        self.assertEqual(len(buffer.chunks), 0)

    def test_resampler_seams_match_one_continuous_conversion_both_directions(self):
        frames = np.sin(np.arange(4800, dtype=np.float32)[:, None] / 15)
        frames = np.repeat(frames, 2, axis=1)
        for incoming, outgoing in ((44100, 48000), (48000, 44100)):
            whole = Resampler(incoming, outgoing, 2).process(frames)
            convert = Resampler(incoming, outgoing, 2)
            chunks = np.concatenate([convert.process(c) for c in np.array_split(frames, 10)])
            np.testing.assert_allclose(chunks, whole, atol=1e-6)

    def test_mono_averages_channels(self):
        stereo = np.array([[1, -1], [0.25, 0.75]], dtype=np.float32)
        np.testing.assert_allclose(stereo_channels(stereo, 1), [[0], [0.5]])
        self.assertIs(stereo_channels(stereo, 2), stereo)

    def test_generated_tones_are_stereo_quiet_and_click_has_silence(self):
        from unix_tones import RATE, tone
        for click in (False, True):
            frames = tone(click)
            self.assertEqual(frames.dtype, np.float32)
            self.assertEqual(frames.shape[1], 2)
            self.assertLessEqual(float(np.abs(frames).max()), 0.151)
        self.assertTrue(np.all(tone(True)[int(RATE * 0.012):] == 0))


class FakeStream:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.active = False
        self.closed = False
        self.written = threading.Event()
        self.data = None

    def start(self):
        self.active = True

    def abort(self):
        self.active = False

    def close(self):
        self.closed = True

    def write(self, data):
        self.data = data.copy()
        self.written.set()


@unittest.skipIf(np is None, "NumPy is optional; install requirements to run Mac stream tests")
class MacTests(unittest.TestCase):
    def setUp(self):
        self.streams = []
        self.core = Mock()
        self.core.device_named.return_value = 9
        self.core.default_output.return_value = 1
        self.sd = types.ModuleType("sounddevice")
        self.sd.query_devices = lambda: [
            {"name": "BlackHole 2ch", "max_input_channels": 2, "max_output_channels": 2,
             "default_samplerate": 48000},
            {"name": "Speakers", "max_input_channels": 0, "max_output_channels": 2,
             "default_samplerate": 48000}]

        def stream(**kwargs):
            item = FakeStream(**kwargs)
            self.streams.append(item)
            return item
        self.sd.InputStream = stream
        self.sd.OutputStream = stream
        self.patchers = [patch.dict(sys.modules, {"sounddevice": self.sd}),
                         patch("coreaudio.CoreAudio", return_value=self.core)]
        for p in self.patchers:
            p.start()
            self.addCleanup(p.stop)
        self.audio = MacAudio("BlackHole")
        self.addCleanup(self.audio.stop)

    def test_blackhole_capture_gain_and_default_restoration(self):
        self.audio.start([{"name": "Speakers", "volume": 25}], {"Speakers": 0})
        self.core.set_default_output.assert_called_with(9)
        self.audio._capture(np.ones((480, 2), dtype=np.float32), 480, None, None)
        self.assertTrue(self.streams[0].written.wait(2))
        np.testing.assert_allclose(self.streams[0].data, 0.25)
        self.audio.sync([{"name": "Speakers", "volume": 0}], {"Speakers": 100})
        self.audio.stop()
        self.core.set_default_output.assert_called_with(1)
        self.assertTrue(all(s.closed for s in self.streams))

    def test_partial_start_restores_default_and_closes_open_streams(self):
        self.sd.InputStream = Mock(side_effect=RuntimeError("capture denied"))
        with self.assertRaisesRegex(RuntimeError, "denied"):
            self.audio.start([{"name": "Speakers"}], {})
        self.audio.stop()
        self.core.set_default_output.assert_called_with(1)
        self.assertTrue(all(s.closed for s in self.streams))

    def test_preexisting_blackhole_default_is_rejected(self):
        self.core.default_output.return_value = 9
        with self.assertRaisesRegex(RuntimeError, "real output"):
            self.audio.start([{"name": "Speakers"}], {})
        self.audio.stop()
        self.core.set_default_output.assert_not_called()

    def test_capture_queue_is_bounded_and_drops_oldest(self):
        import queue
        self.audio.routes = {"test": {"queue": queue.Queue(4)}}
        for i in range(10):
            self.audio._capture(np.full((480, 2), i), 480, None, None)
        q = self.audio.routes["test"]["queue"]
        self.assertEqual(q.qsize(), 4)
        self.assertEqual(q.get()[0, 0], 6)
        self.audio.routes.clear()


class StoreAndPlatformTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-")
        self.addCleanup(self.temp.cleanup)
        config = types.ModuleType("appconfig")
        config.OUTPUTS = []
        config.VIRTUAL_SINK_NAME = "audio_splitter"
        spec = importlib.util.spec_from_file_location("test_store", ROOT / "device_store.py")
        self.store = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"appconfig": config}):
            spec.loader.exec_module(self.store)
        self.store.STORE_FILE = str(Path(self.temp.name) / "settings.json")

    def test_add_remove_last_output_and_persistent_mode_volume_delays(self):
        self.store.add_output("wired")
        self.store.add_output("bluetooth")
        self.store.set_latency("bluetooth", 200)
        self.store.set_volume("wired", 150)
        self.assertEqual(self.store.get_delays(), {"wired": 200, "bluetooth": 0})
        self.assertEqual(self.store.get_outputs()[0]["volume"], 100)
        self.store.set_mode(self.store.VIDEO_MODE)
        outputs = self.store.get_outputs()
        self.assertTrue(outputs[1]["enabled"])
        self.assertFalse(outputs[1]["active"])
        self.store.remove_output("wired")
        self.store.remove_output("bluetooth")
        self.assertEqual(self.store.get_outputs(), [])

    @unittest.skipIf(psutil is None, "psutil is optional; Unix control tests need it")
    def test_device_scan_uses_exact_names_and_rejects_ambiguous_fragments(self):
        self.store.add_output("USB")
        self.store.add_output("wire")
        audio = Mock()
        audio.outputs.return_value = [dict(name=name, is_sink=name == "audio_splitter")
                                      for name in ("USB", "USB headphones", "wired1",
                                                   "wired2", "audio_splitter")]
        scan = unix_control.DeviceScan()
        with patch.dict(sys.modules, {"device_store": self.store}), \
                patch("unix_control.backend", return_value=audio):
            self.assertEqual(scan.connection_status(), {"USB": True, "wire": False})
            self.assertEqual([d["name"] for d in scan.addable_outputs()],
                             ["USB headphones", "wired1", "wired2"])

    @unittest.skipIf(psutil is None, "psutil is optional; Unix control tests need it")
    def test_unix_video_mode_adds_no_fifo_holdback(self):
        self.store.add_output("wired")
        self.store.add_output("hdmi")
        self.store.set_latency("hdmi", 40)
        self.store.set_mode("video")
        with patch.dict(sys.modules, {"device_store": self.store}):
            outputs, delays = unix_control.active_settings()
        self.assertEqual(len(outputs), 2)
        self.assertEqual(delays, {"wired": 0, "hdmi": 0})

    @unittest.skipIf(psutil is None or tkinter is None, "GUI import tests need psutil and Tk")
    def test_gui_windows_imports_stay_windows_unix_imports_stay_unix(self):
        modules = {name: types.ModuleType(name) for name in
                   ("device_scan", "device_store", "mirror_control", "volume_util")}
        with patch.dict(sys.modules, modules), patch.object(sys, "platform", "win32"):
            panel = runpy.run_path(str(ROOT / "app.pyw"))
            for name in modules:
                self.assertIs(panel[name], modules[name])
        with patch.dict(sys.modules, modules), patch.object(sys, "platform", "linux"):
            panel = runpy.run_path(str(ROOT / "app.pyw"))
            self.assertIs(panel["mirror_control"], unix_control.mirror_control)
            self.assertIs(panel["device_scan"], unix_control.device_scan)

    @unittest.skipIf(psutil is None, "psutil is optional; Unix control tests need it")
    def test_worker_pid_reuse_and_other_repository_are_rejected(self):
        state = Path(self.temp.name) / "worker.json"
        state.write_text(json.dumps({"pid": 1000, "created": 10, "ready": True}))
        proc = Mock()
        proc.create_time.return_value = 11
        proc.cmdline.return_value = ["python", str(unix_control.SCRIPT), "--worker"]
        with patch.object(unix_control, "STATE", state), patch("unix_control.psutil.Process", return_value=proc):
            self.assertEqual(unix_control._worker(), (None, None))
            proc.create_time.return_value = 10
            proc.cmdline.return_value = ["python", str(ROOT / "other.py"), "--worker"]
            self.assertEqual(unix_control._worker(), (None, None))
            proc.cmdline.return_value = ["python", str(unix_control.SCRIPT), "--worker"]
            self.assertIs(unix_control._worker()[0], proc)

    @unittest.skipIf(psutil is None, "psutil is optional; Unix control tests need it")
    def test_cli_routes_list_status_and_toggle_without_windows_imports(self):
        import contextlib
        import io
        audio = Mock()
        audio.outputs.return_value = [{"name": "wired", "label": "Wired", "is_sink": False}]
        control = Mock()
        control.is_running.return_value = False
        with patch.object(sys, "platform", "linux"), \
                patch("unix_control.backend", return_value=audio), \
                patch("unix_control.mirror_control", control), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            unix_audio.main(["list"])
            unix_audio.main(["status"])
            unix_audio.main(["toggle"])
            self.assertIn("wired", output.getvalue())
            self.assertIn("OFF", output.getvalue())
        control.start.assert_called_once()
        control.stop.assert_not_called()

    @unittest.skipIf(psutil is None, "psutil is optional; Unix control tests need it")
    def test_start_failure_cleans_up_exited_worker(self):
        child = Mock()
        child.poll.return_value = 1
        controller = unix_control.MirrorControl()
        with patch("unix_control._worker", return_value=(None, None)), \
                patch("unix_control.subprocess.Popen", return_value=child), \
                patch("pathlib.Path.open", unittest.mock.mock_open()), \
                patch.object(controller, "stop") as stop:
            with self.assertRaisesRegex(RuntimeError, "did not start"):
                controller.start()
            stop.assert_called_once()
        child.terminate.assert_not_called()

    @unittest.skipIf(psutil is None, "psutil is optional; Unix control tests need it")
    def test_start_timeout_cancels_worker_before_state_file_exists(self):
        child = Mock()
        child.poll.return_value = None
        controller = unix_control.MirrorControl()
        with patch("unix_control._worker", return_value=(None, None)), \
                patch("unix_control.subprocess.Popen", return_value=child), \
                patch("unix_control.time.sleep"), \
                patch("pathlib.Path.open", unittest.mock.mock_open()):
            with self.assertRaisesRegex(RuntimeError, "did not start"):
                controller.start()
        child.terminate.assert_called_once()
        child.wait.assert_called_once_with(timeout=10)

    @unittest.skipIf(psutil is None, "psutil is optional; Unix control tests need it")
    def test_worker_cleanup_runs_even_when_start_or_state_write_fails(self):
        fake_fcntl = types.SimpleNamespace(LOCK_EX=1, LOCK_NB=2, flock=lambda *_: None)
        audio = Mock()
        for state_fails in (False, True):
            audio.reset_mock()
            audio.start.side_effect = None if state_fails else RuntimeError("start failed")
            writes = [None, OSError("disk full"), None] if state_fails else [None, None]
            with patch.dict(sys.modules, {"fcntl": fake_fcntl}), \
                    patch.object(unix_audio, "HERE", Path(self.temp.name)), \
                    patch("unix_control.backend", return_value=audio), \
                    patch("unix_control.active_settings", return_value=(OUTPUTS, DELAYS)), \
                    patch("unix_control.write_state", side_effect=writes), \
                    patch("unix_audio.signal.signal"), \
                    patch.object(unix_audio.signal, "SIGHUP", 1, create=True), \
                    patch.object(unix_control, "STATE", Path(self.temp.name) / "worker.json"):
                with self.assertRaises((RuntimeError, OSError)):
                    unix_audio.worker()
            audio.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
