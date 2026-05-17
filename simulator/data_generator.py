# © mifsut.com — industrial-protocol-emulator
# data_generator.py — Funciones de generación de señales industriales realistas

import math
import random
import time


def _t() -> float:
    return time.time()


def sine_wave(min_val: float, max_val: float, period_s: float = 30.0, noise: float = 0.02) -> float:
    """Onda sinusoidal con ruido gaussiano. Simula carga variable."""
    amp = (max_val - min_val) / 2
    center = (max_val + min_val) / 2
    val = center + amp * math.sin(2 * math.pi * _t() / period_s)
    val += random.gauss(0, amp * noise)
    return round(max(min_val, min(max_val, val)), 3)


def ramp(min_val: float, max_val: float, period_s: float = 60.0) -> float:
    """Rampa triangular ascendente/descendente."""
    t = _t() % period_s
    half = period_s / 2
    if t < half:
        val = min_val + (max_val - min_val) * (t / half)
    else:
        val = max_val - (max_val - min_val) * ((t - half) / half)
    return round(val, 3)


def random_walk(min_val: float, max_val: float, step: float = 0.5) -> float:
    """Paseo aleatorio — simula sensor con deriva lenta."""
    center = (max_val + min_val) / 2
    val = center + random.uniform(-step, step) * (max_val - min_val) / 4
    return round(max(min_val, min(max_val, val)), 3)


def constant(val: float, noise: float = 0.01) -> float:
    """Valor constante con pequeño ruido."""
    return round(val + random.gauss(0, abs(val) * noise), 3)


# Rangos industriales estándar por unidad
UNIT_RANGES = {
    "Hz":    (0.0,   60.0),
    "A":     (0.0,   100.0),
    "V":     (200.0, 480.0),
    "°C":    (-20.0, 150.0),
    "kW":    (0.0,   500.0),
    "rpm":   (0.0,   3000.0),
    "bar":   (0.0,   10.0),
    "m3/h":  (0.0,   100.0),
    "%":     (0.0,   100.0),
    "W":     (0.0,   5000.0),
    "kWh":   (0.0,   99999.0),
    "Pa":    (0.0,   10000.0),
    "lux":   (0.0,   1000.0),
    "":      (0.0,   100.0),
}


def get_signal(tag_id: str, unit: str, override: dict | None = None) -> float:
    """
    Genera un valor para el tag dado su unidad.
    Si override contiene {min, max, pattern}, usa esos parámetros.
    """
    if override:
        lo = override.get("min", 0.0)
        hi = override.get("max", 100.0)
        pattern = override.get("pattern", "sine")
    else:
        lo, hi = UNIT_RANGES.get(unit, (0.0, 100.0))
        pattern = "sine"

    if pattern == "ramp":
        return ramp(lo, hi)
    elif pattern == "random":
        return random_walk(lo, hi)
    elif pattern == "constant":
        mid = (lo + hi) / 2
        return constant(mid)
    else:  # sine (default)
        return sine_wave(lo, hi)
