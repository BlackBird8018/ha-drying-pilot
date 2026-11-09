# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

import random
from datetime import datetime, timedelta, timezone

from cdt.calibration import Observation, Run, Sample, fit, progress_from_trace
from cdt.model import Location, ModelParams, Weather, drying_rate, humid_enter, penman_weights, dew_risk

P = ModelParams()
T0 = datetime(2026, 7, 4, 8, 0, tzinfo=timezone.utc)


def test_penman_weights_normalised_and_physical():
    aero, rad = penman_weights(P.ref_temp, P.ref_temp)
    assert (round(aero, 6), round(rad, 6)) == (1.0, 1.0)
    cold_aero, cold_rad = penman_weights(5, P.ref_temp)
    warm_aero, warm_rad = penman_weights(25, P.ref_temp)
    assert cold_aero > 1 > warm_aero   # air dryness matters more in the cold
    assert warm_rad > 1 > cold_rad     # sunshine matters more in the warmth


def test_humid_criterion_uses_relative_humidity():
    # 95 % at 25 °C: old VPD rule would not flag it, textiles do take up moisture
    assert humid_enter(Weather(25, 95), P)
    assert not humid_enter(Weather(25, 85), P)


def test_dew_risk_only_on_clear_nights():
    clear_night = Weather(8, 85, sun=0.0, cloud=10)
    cloudy_night = Weather(8, 85, sun=0.0, cloud=90)
    clear_day = Weather(8, 85, sun=0.4, cloud=10)
    assert dew_risk(clear_night, P)
    assert not dew_risk(cloudy_night, P)
    assert not dew_risk(clear_day, P)


def _simulate_run(rng, day, k_true, f_true, model=P):
    start = T0 + timedelta(days=day)
    run = Run(start=start, location=Location.LINE, laundry="normal", target=100.0)
    t, temp, rh, wind, sun = start, rng.uniform(14, 26), rng.uniform(45, 75), rng.uniform(4, 22), rng.uniform(0, 0.8)
    for i in range(48):  # 12 h in 15 min steps
        run.add_sample(Sample(t + timedelta(minutes=15 * i), temp, rh, wind, sun, "sensor"))
    truth = ModelParams(k=k_true, wind_factor=f_true)
    real_target = 100 * rng.lognormvariate(0, 0.1)
    rate_true = drying_rate(Weather(temp, rh, wind, sun), Location.LINE, truth)
    rate_model = drying_rate(Weather(temp, rh, wind, sun), Location.LINE, model)
    t_model = start + timedelta(hours=100 / rate_model)
    t_true = start + timedelta(hours=real_target / rate_true)
    run.observations.append(Observation(t_model, t_true <= t_model))
    return run


def test_fit_recovers_true_factors():
    """Adaptive like in real use: each question is asked at the calibrated time."""
    rng = random.Random(4)
    runs, model = [], P
    for d in range(40):
        runs.append(_simulate_run(rng, d, 0.8, 0.5, model))
        r = fit(runs, Location.LINE, P)
        model = ModelParams(k=r.k, wind_factor=r.wind_factor)
    result = fit(runs, Location.LINE, P)
    assert result.answers == 40 and result.calibrated
    assert 0.65 < result.k < 0.95
    assert result.wind_factor < 0.9


def test_fit_without_data_is_neutral():
    result = fit([], Location.LINE, P)
    assert (result.k, result.wind_factor, result.answers) == (1.0, 1.0, 0)


def test_answers_after_rewetting_or_24h_are_ignored():
    run = Run(start=T0, location=Location.LINE, laundry="normal", target=100.0)
    run.observations = [
        Observation(T0 + timedelta(hours=3), False),
        Observation(T0 + timedelta(hours=10), True),
        Observation(T0 + timedelta(hours=30), True),
    ]
    run.rewet_at = T0 + timedelta(hours=8)
    assert [o.time for o in run.valid_observations()] == [T0 + timedelta(hours=3)]
    run.excluded = "unknown"
    assert run.valid_observations() == []


def test_other_location_and_reset_marker():
    rng = random.Random(1)
    runs = [_simulate_run(rng, d, 0.7, 1.0) for d in range(10)]
    assert fit(runs, Location.COVERED, P).answers == 0
    assert fit(runs, Location.LINE, P, since=T0 + timedelta(days=100)).answers == 0


def test_damp_answer_lowers_k_and_progress():
    run = Run(start=T0, location=Location.LINE, laundry="normal", target=100.0)
    for i in range(20):
        run.add_sample(Sample(T0 + timedelta(minutes=15 * i), 22, 50, 10, 0.5, "sensor"))
    rate = drying_rate(Weather(22, 50, 10, 0.5), Location.LINE, P)
    t_dry = T0 + timedelta(hours=100 / rate)
    run.observations.append(Observation(t_dry, False))
    result = fit([run], Location.LINE, P)
    assert result.k < 1.0
    calibrated = ModelParams(k=result.k, wind_factor=result.wind_factor)
    assert progress_from_trace(run, t_dry, calibrated) < 100


def test_roundtrip_storage():
    run = _simulate_run(random.Random(2), 0, 1.0, 1.0)
    again = Run.from_dict(run.to_dict())
    assert again.to_dict() == run.to_dict()


def test_samples_are_thinned_to_15_minutes():
    run = Run(start=T0, location=Location.LINE, laundry="normal", target=100.0)
    for i in range(12):  # every 5 minutes for 1 h
        run.add_sample(Sample(T0 + timedelta(minutes=5 * i), 20, 50, 5, 0, "sensor"))
    assert len(run.samples) == 4
