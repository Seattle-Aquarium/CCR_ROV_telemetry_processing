"""
One flight, recorded from arming to disarming, without anyone pressing a button.

What this writes into a flight's ``logs`` folder, per flight:

===========================  ==================================================
``laptop_monitor_*.csv``     the topside at 1 Hz, one row a second
``laptop_monitor_*.json``    what those columns mean and which this machine
                             could actually fill
``params_*.json``            every autopilot parameter as it stood at disarming
``delta_params_*.json/txt``  the ones that moved during the flight, with the
                             value before and the value after
``versions_*.json``          BlueOS, ArduSub, the board and every extension
``delta_versions_*.json/txt``  the ones that moved during the flight
===========================  ==================================================

**Arming is the trigger, not a button.** The pilot arms to fly and disarms when
they are done; that is already the truth of when a flight happened, recorded by
the autopilot. Asking someone to also press Start here would mean the record is
missing on exactly the busy days it matters most. Arm state is read from the
HEARTBEAT mavlink2rest already holds, so watching it costs one small GET every
couple of seconds and sends the vehicle nothing.

**A brief disarm does not end a flight.** Sitting on the surface between
transects, a bump of the arm switch, a failsafe that trips and clears -- all of
these disarm the vehicle without the dive being over. Ending the flight on the
first disarm would cut one dive into four files with four sets of parameters,
none of which answers "what was set on that dive?". So a disarm opens a grace
period, and only its expiry closes the flight. Re-arming inside it carries on
the same recording, and the gap is noted in the companion file rather than
hidden.

**A dropped request is not a disarm.** `read_arm_state` returns None when it
cannot tell, and None never ends a flight. The tether drops packets -- this
programme has measured it doing so -- and a recorder that stopped on one lost
GET would stop mid-transect.

**Nothing here can fail a flight.** Every write is best-effort and every read is
wrapped. The worst outcome is a missing column or a missing file, never a
traceback in front of someone flying an ROV.
"""

from __future__ import annotations

import csv
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import blueos, laptop
from . import wincounters as W

#: How often the vehicle is asked whether it is armed. Two seconds is well
#: inside the grace period and costs the Pi one small GET; a faster poll would
#: buy nothing but load on a machine that is recording a dive.
ARM_POLL_S = 2.0

#: How often the Pi's own temperature and throttle state are read. Slower than
#: the arm poll because it moves slowly, and it is carried into every 1 Hz row
#: regardless -- held forward between reads rather than interpolated.
PI_POLL_S = 5.0

#: How long a disarm must stand before the flight is considered over.
#: Ninety seconds covers a surface interval between transects and a failsafe
#: that clears, and is short enough that the closing snapshot is taken while
#: the vehicle is still on the tether.
DISARM_GRACE_S = 90.0

#: Rows are written as they are sampled but flushed on this cadence, so a
#: laptop that dies mid-dive loses seconds rather than the flight.
FLUSH_EVERY_S = 10.0


def _stamp(when: float | None = None) -> str:
    """`2026-09-11_1305`, local time -- the field's own clock."""
    return datetime.fromtimestamp(when or time.time()).strftime("%Y-%m-%d_%H%M")


def _iso(when: float) -> str:
    return datetime.fromtimestamp(when, timezone.utc).isoformat(
        timespec="seconds")


@dataclass
class Snapshot:
    """The vehicle's configuration at one instant."""

    taken: float = 0.0
    parameters: dict = field(default_factory=dict)
    parameters_from: str = ""
    versions: dict = field(default_factory=dict)
    dataflash_log: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.parameters) or bool(self.versions)


@dataclass
class Status:
    """What the recorder is doing, for the page that shows it."""

    state: str = "idle"          # idle | recording | closing | disconnected
    armed: bool | None = None
    flight_id: str = ""
    rows: int = 0
    started: float = 0.0
    since_disarm: float | None = None
    csv_path: Path | None = None
    by_hand: bool = False
    note: str = ""
    problem: str = ""

    def line(self) -> str:
        if self.problem:
            return self.problem
        if self.state == "recording":
            mins = (time.time() - self.started) / 60 if self.started else 0
            if self.by_hand:
                tail = "   started by hand — press Stop to close it"
            elif self.since_disarm is None:
                tail = ""
            else:
                tail = (f"   disarmed {self.since_disarm:.0f}s ago, closing in "
                        f"{max(0, DISARM_GRACE_S - self.since_disarm):.0f}s")
            return (f"Recording {self.flight_id} — {self.rows:,} rows, "
                    f"{mins:.1f} min{tail}")
        if self.state == "closing":
            return f"Closing {self.flight_id} — reading the vehicle…"
        if self.armed is None:
            return "Waiting for the vehicle. Nothing is being recorded."
        return "Waiting for the ROV to arm. Nothing is being recorded."


class FlightRecorder:
    """Watches for arming, and records a flight when it happens.

    Owns its own threads rather than going through the application's single
    worker: that worker is for jobs with a beginning and an end and refuses to
    start a second, and a recorder that blocked the operator from fetching
    files for the length of a dive would be worse than no recorder.
    """

    def __init__(self, *, host: str = "192.168.2.2",
                 flight_dir: Path | None = None,
                 on_change=None):
        self.host = host
        self.flight_dir = Path(flight_dir) if flight_dir else None
        #: Called on any state change, from a worker thread. The GUI must
        #: marshal it onto the main thread itself -- Tk is not thread-safe.
        self.on_change = on_change

        self.status = Status()
        self.history = laptop.History()
        self.capabilities: dict[str, str] = {}

        self._sampler: laptop.Sampler | None = None
        self._fh = None
        self._writer = None
        self._rows = 0
        self._flushed_at = 0.0

        self._start_snap = Snapshot()
        self._log_at_arm = ""
        self._gaps: list[dict] = []
        self._disarm_at: float | None = None
        #: A flight begun by hand is ended by hand. The override exists for
        #: when arm detection is the thing that is not working -- a bench
        #: test, a vehicle whose MAVLink router has died -- so letting the
        #: disarm watcher close it would defeat the point. It closed a manual
        #: recording ninety seconds in the first time this was tried.
        self._manual = False

        self._stop = threading.Event()
        self._watch: threading.Thread | None = None
        self._sample: threading.Thread | None = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    #  lifecycle
    # ------------------------------------------------------------------

    def start_watching(self) -> None:
        """Begin watching for arming. Records nothing until the ROV arms."""
        if self._watch is not None:
            return
        self._stop.clear()
        self.capabilities = W.capabilities()
        self._watch = threading.Thread(target=self._watch_loop, daemon=True,
                                       name="utc-arm-watch")
        self._watch.start()

    def stop_watching(self, *, finish: bool = True) -> None:
        """Stop watching. An open flight is closed properly unless told not to."""
        self._stop.set()
        if self._watch is not None:
            self._watch.join(timeout=5.0)
            self._watch = None
        if self.status.state == "recording":
            if finish:
                self._end_flight(reason="monitoring stopped")
            else:
                self._close_csv()

    @property
    def watching(self) -> bool:
        return self._watch is not None and self._watch.is_alive()

    def _changed(self) -> None:
        if self.on_change is not None:
            try:
                self.on_change()
            except Exception:
                pass

    # ------------------------------------------------------------------
    #  the watcher
    # ------------------------------------------------------------------

    def _watch_loop(self) -> None:
        last_pi = 0.0
        while not self._stop.is_set():
            try:
                armed, ms = blueos.read_arm_state(self.host)
                self.status.armed = armed
                if self._sampler is not None:
                    self._sampler.vehicle.reachable = ms is not None
                    self._sampler.vehicle.armed = armed
                    self._sampler.vehicle.http_ms = ms

                if time.monotonic() - last_pi > PI_POLL_S:
                    last_pi = time.monotonic()
                    self._read_pi()

                if armed is True:
                    self._on_armed()
                elif armed is False:
                    self._on_disarmed()
                # armed is None: the vehicle did not answer. Deliberately no
                # action -- an unanswered question is not a disarm.
                self._changed()
            except Exception:
                pass
            self._stop.wait(ARM_POLL_S)

    def _read_pi(self) -> None:
        if self._sampler is None:
            return
        try:
            soc, _peak = blueos.read_temperature(self.host)
            self._sampler.vehicle.soc_temp_c = soc
        except Exception:
            pass

    def _on_armed(self) -> None:
        with self._lock:
            if self.status.state == "recording":
                if self._disarm_at is not None:
                    # Re-armed inside the grace period: one flight, with a gap
                    # in it that is recorded rather than smoothed over.
                    self._gaps.append({
                        "disarmed": _iso(self._disarm_at),
                        "rearmed": _iso(time.time()),
                        "seconds": round(time.time() - self._disarm_at, 1)})
                    self._disarm_at = None
                    self.status.since_disarm = None
                return
            if self.status.state != "idle":
                return
            self._begin_flight()

    def _on_disarmed(self) -> None:
        with self._lock:
            if self.status.state != "recording" or self._manual:
                return
            if self._disarm_at is None:
                self._disarm_at = time.time()
            self.status.since_disarm = time.time() - self._disarm_at
            if self.status.since_disarm >= DISARM_GRACE_S:
                self._end_flight(reason="disarmed")

    # ------------------------------------------------------------------
    #  a flight
    # ------------------------------------------------------------------

    def _begin_flight(self) -> None:
        """Open the CSV and start sampling. Called with the lock held."""
        folder = self._logs_dir()
        if folder is None:
            # The operator chose that a flight without a folder should not be
            # silently filed somewhere else. Say so loudly and keep watching:
            # choosing a folder mid-dive still catches the rest of it.
            self.status.problem = (
                ("Nothing is being recorded. " if self._manual else
                 "THE ROV IS ARMED AND NOTHING IS BEING RECORDED. ")
                + "Choose a flight folder on Flight & transects — the monitor "
                  "writes into its logs folder and will not guess one.")
            return
        self.status.problem = ""
        now = time.time()
        stamp = _stamp(now)
        self.status.flight_id = stamp
        self.status.started = now
        self.status.rows = 0
        self._rows = 0
        self._gaps = []
        self._disarm_at = None
        self.status.since_disarm = None
        self.history.clear()

        path = folder / f"laptop_monitor_{stamp}.csv"
        try:
            self._fh = path.open("w", newline="", encoding="utf-8")
            self._writer = csv.DictWriter(self._fh, fieldnames=laptop.COLUMNS,
                                          extrasaction="ignore")
            self._writer.writeheader()
            self._fh.flush()
        except Exception as ex:
            self.status.problem = f"Could not open {path.name}: {ex}"
            self._fh = None
            return
        self.status.csv_path = path
        self._flushed_at = time.monotonic()

        self._sampler = laptop.Sampler(rov_host=self.host, flight_id=stamp)
        self._sampler.start()
        self.status.state = "recording"

        self._sample = threading.Thread(target=self._sample_loop, daemon=True,
                                        name="utc-sampler")
        self._sample.start()

        # The opening snapshot is a download, so it runs on its own thread and
        # the recording does not wait for it.
        threading.Thread(target=self._capture_start, daemon=True,
                         name="utc-snap-start").start()
        self._changed()

    def _sample_loop(self) -> None:
        """One row a second, on a fixed cadence rather than a drifting sleep."""
        tick = time.monotonic()
        while not self._stop.is_set() and self.status.state == "recording":
            tick += laptop.DEFAULT_PERIOD_S
            try:
                sampler = self._sampler
                if sampler is None:
                    break
                row = sampler.sample()
                self.history.add(row)
                if self._writer is not None:
                    self._writer.writerow(row)
                    self._rows += 1
                    self.status.rows = self._rows
                    if time.monotonic() - self._flushed_at > FLUSH_EVERY_S:
                        self._fh.flush()
                        self._flushed_at = time.monotonic()
            except Exception:
                pass
            # Sleeping to the next tick rather than for a second keeps the
            # cadence honest when a sample runs long.
            time.sleep(max(0.0, tick - time.monotonic()))

    def _capture_start(self) -> None:
        self._start_snap = self._snapshot()
        self._log_at_arm = self._start_snap.dataflash_log
        self._changed()

    def _snapshot(self, since_log: str = "") -> Snapshot:
        """Read the vehicle's parameters and versions. Never raises."""
        snap = Snapshot(taken=time.time())
        try:
            token = blueos.file_token(self.host)
            snap.dataflash_log = blueos.newest_dataflash(self.host, token)
            snap.parameters, snap.parameters_from = blueos.read_parameters_now(
                self.host, token, since_log=since_log)
        except Exception:
            pass
        try:
            snap.versions = blueos.read_versions(self.host)
        except Exception:
            pass
        return snap

    def _end_flight(self, *, reason: str) -> None:
        """Close the CSV, take the closing snapshot, write the deltas."""
        if self.status.state != "recording":
            return
        self.status.state = "closing"
        self._changed()
        if self._sample is not None:
            self._sample.join(timeout=5.0)
            self._sample = None
        self._close_csv()
        if self._sampler is not None:
            self._sampler.stop()
            self._sampler = None

        end = self._snapshot(since_log=self._log_at_arm)
        try:
            self._write_files(end, reason=reason)
        except Exception as ex:
            self.status.problem = f"Could not write the flight files: {ex}"
        self.status.state = "idle"
        self.status.since_disarm = None
        self._disarm_at = None
        self._manual = False
        self.status.by_hand = False
        self._changed()

    def _close_csv(self) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
                self._fh.close()
            except Exception:
                pass
        self._fh = None
        self._writer = None

    # ------------------------------------------------------------------
    #  what lands in logs/
    # ------------------------------------------------------------------

    def _logs_dir(self) -> Path | None:
        if not self.flight_dir:
            return None
        try:
            out = Path(self.flight_dir) / "logs"
            out.mkdir(parents=True, exist_ok=True)
            return out
        except Exception:
            return None

    def _write_files(self, end: Snapshot, *, reason: str) -> None:
        folder = self._logs_dir()
        if folder is None:
            return
        stamp = self.status.flight_id
        start = self._start_snap

        # ---- the CSV's companion ------------------------------------
        _write_json(folder / f"laptop_monitor_{stamp}.json", {
            "flight_id": stamp,
            "started": _iso(self.status.started),
            "ended": _iso(time.time()),
            "ended_because": reason,
            "rows": self._rows,
            "sample_period_s": laptop.DEFAULT_PERIOD_S,
            "computer_name": self._computer_name(),
            "rov_host": self.host,
            "rov_interface": self._interface_name(),
            "disarm_grace_s": DISARM_GRACE_S,
            "brief_disarms": self._gaps,
            "columns": list(laptop.COLUMNS),
            "units": laptop.UNITS,
            # Why a column is blank, so nobody has to guess at it later.
            "readings_available_on_this_machine": self.capabilities,
        })

        # ---- parameters ----------------------------------------------
        if end.parameters:
            _write_json(folder / f"params_{stamp}.json", {
                "taken": _iso(end.taken),
                "read_from": end.parameters_from,
                "count": len(end.parameters),
                "source": "ArduPilot dataflash log (read-only)",
                "parameters": end.parameters,
            })
        if start.parameters and end.parameters:
            delta = blueos.diff_parameters(start.parameters, end.parameters)
            _write_json(folder / f"delta_params_{stamp}.json", {
                "flight_id": stamp,
                "before_taken": _iso(start.taken),
                "after_taken": _iso(end.taken),
                "before_read_from": start.parameters_from,
                "after_read_from": end.parameters_from,
                "changed": len(delta),
                "changes": {k: {"before": a, "after": b,
                                "set_by_autopilot": blueos.is_automatic(k)}
                            for k, (a, b) in delta.items()},
            })
            (folder / f"delta_params_{stamp}.txt").write_text(
                _params_table(delta, stamp, start, end), encoding="utf-8")

        # ---- versions -------------------------------------------------
        if end.versions:
            _write_json(folder / f"versions_{stamp}.json", {
                "taken": _iso(end.taken),
                "versions": end.versions,
            })
        if start.versions and end.versions:
            vdelta = blueos.diff_versions(start.versions, end.versions)
            _write_json(folder / f"delta_versions_{stamp}.json", {
                "flight_id": stamp,
                "before_taken": _iso(start.taken),
                "after_taken": _iso(end.taken),
                "changed": len(vdelta),
                "changes": {k: {"before": a, "after": b}
                            for k, (a, b) in vdelta.items()},
            })
            (folder / f"delta_versions_{stamp}.txt").write_text(
                _versions_table(vdelta, stamp, start, end), encoding="utf-8")

    def _computer_name(self) -> str:
        import socket
        return socket.gethostname()

    def _interface_name(self) -> str:
        try:
            return laptop.find_rov_interface(self.host) or ""
        except Exception:
            return ""

    # ------------------------------------------------------------------
    #  manual override
    # ------------------------------------------------------------------

    def start_manually(self) -> bool:
        """Begin a flight without waiting for the ROV to arm."""
        with self._lock:
            if self.status.state != "idle":
                return False
            self._manual = True
            self.status.by_hand = True
            self._begin_flight()
            if self.status.state != "recording":
                self._manual = False
                self.status.by_hand = False
            return self.status.state == "recording"

    def stop_manually(self) -> bool:
        """End the flight now, without waiting out the grace period."""
        with self._lock:
            if self.status.state != "recording":
                return False
            threading.Thread(
                target=lambda: self._end_flight(reason="stopped by hand"),
                daemon=True, name="utc-end-flight").start()
            return True


# --------------------------------------------------------------------------
#  the human-readable halves
# --------------------------------------------------------------------------


def _write_json(path: Path, payload: dict) -> None:
    try:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True,
                                   default=str), encoding="utf-8")
    except Exception:
        pass


def _params_table(delta: dict, stamp: str, start: Snapshot,
                  end: Snapshot) -> str:
    """The parameter changes as a table somebody can read on deck.

    The ones ArduPilot sets itself are listed apart. Barometer ground pressure
    is re-zeroed at every arming, so it changes on every flight; leaving it in
    the main list would mean the file always looks as though something was
    changed, and the one flight where something actually was would look the
    same as all the others.
    """
    by_hand = {k: v for k, v in delta.items() if not blueos.is_automatic(k)}
    by_itself = {k: v for k, v in delta.items() if blueos.is_automatic(k)}

    out = [
        f"ArduSub parameter changes during flight {stamp}",
        "=" * 64,
        f"before : {_iso(start.taken)}   from {start.parameters_from or '?'}"
        f"   ({len(start.parameters):,} parameters)",
        f"after  : {_iso(end.taken)}   from {end.parameters_from or '?'}"
        f"   ({len(end.parameters):,} parameters)",
        "",
    ]
    if not delta:
        out.append("Nothing changed during this flight.")
        return "\n".join(out) + "\n"

    if by_hand:
        out += [f"CHANGED DURING THE FLIGHT  ({len(by_hand)})", "-" * 64]
        out += [_param_line(k, a, b) for k, (a, b) in by_hand.items()]
        out.append("")
    else:
        out += ["No parameter was changed by hand during this flight.", ""]
    if by_itself:
        out += [f"set by the autopilot itself  ({len(by_itself)})",
                "-" * 64]
        out += [_param_line(k, a, b) for k, (a, b) in by_itself.items()]
        out.append("")
    return "\n".join(out) + "\n"


def _param_line(name: str, before, after) -> str:
    return (f"  {name:<24s} {_v(before):>18s}  ->  {_v(after):<18s}"
            + ("   (added)" if before is None else
               "   (removed)" if after is None else ""))


def _v(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        # Trailing zeros on a parameter read as significance it does not have.
        return f"{value:.10g}"
    return str(value)


def _versions_table(delta: dict, stamp: str, start: Snapshot,
                    end: Snapshot) -> str:
    out = [
        f"Software version changes during flight {stamp}",
        "=" * 64,
        f"before : {_iso(start.taken)}",
        f"after  : {_iso(end.taken)}",
        "",
    ]
    if not delta:
        out += ["Nothing changed during this flight.", "",
                "Versions as flown:", "-" * 64]
        v = end.versions or start.versions
        out += [f"  {'BlueOS':<28s} {v.get('blueos', '?')}",
                f"  {'ArduSub':<28s} {v.get('ardusub', '?')} "
                f"({v.get('ardusub_type', '')})",
                f"  {'board':<28s} {v.get('board', '?')}"]
        for e in v.get("extensions") or []:
            mark = "" if e.get("enabled", True) else "   (disabled)"
            out.append(f"  {('ext: ' + str(e.get('name', ''))):<28s} "
                       f"{e.get('tag', '')}{mark}")
        return "\n".join(out) + "\n"

    out += [f"CHANGED DURING THE FLIGHT  ({len(delta)})", "-" * 64]
    for name, (a, b) in delta.items():
        out.append(f"  {name:<34s} {_v(a):>22s}  ->  {_v(b)}")
    out.append("")
    return "\n".join(out) + "\n"
