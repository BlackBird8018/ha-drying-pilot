# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""Self-calibration from user feedback (no HA dependency).

Each drying run stores the raw weather trace and the user's answers
("dry" / "still damp" at a given time). From all valid answers a posterior
over two factors per location is computed on a grid:

    rate = k * (P + wind_factor * Q)          (see model.rate_terms)

* k           overall factor (load, fabric, shading, ...)
* wind_factor share of the forecast wind that reaches the drying spot

An answer "dry at t" means the accumulated drying reached the target before t,
"damp at t" means it did not. The real target scatters from load to load
(lognormal, SIGMA), which turns each answer into a smooth likelihood.
Priors keep both factors near 1 until the data says otherwise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .model import Location, ModelParams, Weather, rate_terms

SIGMA = 0.12  # scatter of the real target from load to load (log)
PRIOR_LOG_K_SD = 0.5
PRIOR_WIND_MEAN = 1.0
PRIOR_WIND_SD = 0.35
MAX_RUN_DURATION = timedelta(hours=24)
MIN_SAMPLE_GAP = timedelta(minutes=15)
MAX_RUNS = 200
CALIBRATED_AFTER = 5  # answers until the status says "calibrated"

K_GRID = [0.4 * (2.5 / 0.4) ** (i / 47) for i in range(48)]
WIND_GRID = [0.2 + 0.05 * i for i in range(29)]  # 0.2 .. 1.6


@dataclass
class Sample:
    time: datetime
    temperature: float
    humidity: float
    wind_kmh: float
    sun: float
    source: str  # "sensor" or "forecast"

    def to_list(self) -> list:
        return [
            self.time.isoformat(),
            round(self.temperature, 2),
            round(self.humidity, 1),
            round(self.wind_kmh, 1),
            round(self.sun, 3),
            self.source,
        ]

    @classmethod
    def from_list(cls, data: list) -> Sample:
        return cls(datetime.fromisoformat(data[0]), *data[1:6])

    @property
    def weather(self) -> Weather:
        return Weather(self.temperature, self.humidity, self.wind_kmh, self.sun)


@dataclass
class Observation:
    time: datetime
    dry: bool

    def to_list(self) -> list:
        return [self.time.isoformat(), self.dry]

    @classmethod
    def from_list(cls, data: list) -> Observation:
        return cls(datetime.fromisoformat(data[0]), bool(data[1]))


@dataclass
class Run:
    """One drying run: from hanging out until brought in."""

    start: datetime
    location: Location
    laundry: str
    target: float
    samples: list[Sample] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    rewet_at: datetime | None = None  # first rain / rewetting during the run
    end: datetime | None = None
    excluded: str | None = None  # reason if the run must not be used

    # ------------------------------------------------------------- recording

    def add_sample(self, sample: Sample) -> None:
        if self.samples and sample.time - self.samples[-1].time < MIN_SAMPLE_GAP:
            return
        self.samples.append(sample)

    def valid_observations(self) -> list[Observation]:
        """Answers that may be used for calibration."""
        if self.excluded:
            return []
        limit = self.start + MAX_RUN_DURATION
        if self.rewet_at is not None:
            limit = min(limit, self.rewet_at)
        return [o for o in self.observations if self.start < o.time <= limit]

    # ------------------------------------------------------------- storage

    def to_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
            "location": self.location.value,
            "laundry": self.laundry,
            "target": self.target,
            "samples": [s.to_list() for s in self.samples],
            "observations": [o.to_list() for o in self.observations],
            "rewet_at": self.rewet_at.isoformat() if self.rewet_at else None,
            "excluded": self.excluded,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Run:
        def dt(value: str | None) -> datetime | None:
            return datetime.fromisoformat(value) if value else None

        return cls(
            start=datetime.fromisoformat(data["start"]),
            end=dt(data.get("end")),
            location=Location(data["location"]),
            laundry=data.get("laundry", "normal"),
            target=float(data["target"]),
            samples=[Sample.from_list(s) for s in data.get("samples", [])],
            observations=[Observation.from_list(o) for o in data.get("observations", [])],
            rewet_at=dt(data.get("rewet_at")),
            excluded=data.get("excluded"),
        )


def accumulated_terms(
    run: Run, until: datetime, params: ModelParams
) -> tuple[float, float]:
    """Integrate P and Q (see model.rate_terms) from the run start until `until`."""
    p_sum = q_sum = 0.0
    samples = run.samples
    for i, sample in enumerate(samples):
        if sample.time >= until:
            break
        seg_end = samples[i + 1].time if i + 1 < len(samples) else until
        seg_end = min(seg_end, until)
        hours = (seg_end - sample.time).total_seconds() / 3600.0
        if hours <= 0:
            continue
        p, q = rate_terms(sample.weather, run.location, params)
        p_sum += p * hours
        q_sum += q * hours
    return p_sum, q_sum


def _log_phi(z: float) -> float:
    """log of the standard normal CDF, numerically safe."""
    return math.log(max(0.5 * math.erfc(-z / math.sqrt(2.0)), 1e-300))


@dataclass(frozen=True)
class CalibrationResult:
    k: float = 1.0
    wind_factor: float = 1.0
    k_uncertainty: float = PRIOR_LOG_K_SD  # relative (1 sigma, log scale)
    answers: int = 0
    runs: int = 0

    @property
    def calibrated(self) -> bool:
        return self.answers >= CALIBRATED_AFTER


def fit(
    runs: list[Run],
    location: Location,
    params: ModelParams,
    since: datetime | None = None,
) -> CalibrationResult:
    """Posterior mean of k and wind_factor for one location."""
    data: list[tuple[float, float, float, bool]] = []
    used_runs = 0
    for run in runs:
        if run.location is not location or (since and run.start < since):
            continue
        obs = run.valid_observations()
        if not obs:
            continue
        used_runs += 1
        for o in obs:
            p, q = accumulated_terms(run, o.time, params)
            data.append((p, q, run.target, o.dry))
    if not data:
        return CalibrationResult()

    log_post: list[tuple[float, float, float]] = []
    for k in K_GRID:
        prior_k = -0.5 * (math.log(k) / PRIOR_LOG_K_SD) ** 2
        for f in WIND_GRID:
            lp = prior_k - 0.5 * ((f - PRIOR_WIND_MEAN) / PRIOR_WIND_SD) ** 2
            for p, q, target, dry in data:
                acc = k * (p + f * q)
                z = (math.log(max(acc, 1e-9)) - math.log(target)) / SIGMA
                lp += _log_phi(z) if dry else _log_phi(-z)
            log_post.append((lp, k, f))

    top = max(lp for lp, _, _ in log_post)
    weights = [(math.exp(lp - top), k, f) for lp, k, f in log_post]
    total = sum(w for w, _, _ in weights)
    mean_log_k = sum(w * math.log(k) for w, k, _ in weights) / total
    mean_f = sum(w * f for w, _, f in weights) / total
    var_log_k = sum(w * (math.log(k) - mean_log_k) ** 2 for w, k, _ in weights) / total
    return CalibrationResult(
        k=math.exp(mean_log_k),
        wind_factor=mean_f,
        k_uncertainty=math.sqrt(var_log_k),
        answers=len(data),
        runs=used_runs,
    )


def progress_from_trace(run: Run, now: datetime, params: ModelParams) -> float:
    """Recompute the progress of a run from its trace with the given factors."""
    p, q = accumulated_terms(run, now, params)
    return params.k * (p + params.wind_factor * q)
