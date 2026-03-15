import math


def clamp_input_value(value: int) -> int:
    """Omezí syrovou hodnotu do rozsahu 0 až 1023."""
    if value < 0:
        return 0

    if value > 1023:
        return 1023

    return value


def analog_to_temperature_c(value: int) -> float:
    """Převede syrovou analogovou hodnotu na přibližnou teplotu v °C.

    Tady je použitý zjednodušený beta model termistoru.
    Hodnota je chápána stejně jako na Arduino ADC 0 až 1023.
    """
    value = clamp_input_value(value)

    if value <= 0:
        value = 1

    if value >= 1023:
        value = 1022

    beta = 3950.0
    reference_temperature_k = 298.15
    reference_resistance = 10000.0
    series_resistor = 10000.0

    resistance = series_resistor * (1023.0 / value - 1.0)

    if resistance <= 0:
        resistance = 1.0

    temp_k = 1.0 / (
        (1.0 / reference_temperature_k)
        + (1.0 / beta) * math.log(resistance / reference_resistance)
    )
    temp_c = temp_k - 273.15

    return round(temp_c, 2)


def analog_to_lux(value: int) -> float:
    """Převede syrovou hodnotu osvětlení na přibližné luxy."""
    value = clamp_input_value(value)
    lux = (value / 1023.0) * 1000.0
    return round(lux, 2)


def analog_to_humidity_percent(value: int) -> float:
    """Převede syrovou hodnotu na přibližnou vlhkost v procentech."""
    value = clamp_input_value(value)
    humidity = (value / 1023.0) * 100.0
    return round(humidity, 2)


def analog_to_noise_db(value: int) -> float:
    """Převede syrovou hodnotu na orientační relativní hluk v dB."""
    value = clamp_input_value(value)
    db = 30.0 + (value / 1023.0) * 70.0
    return round(db, 2)


def convert_sensor_value(peripheral_id: str, raw_value: int):
    """Vrátí přepočtenou hodnotu a jednotku podle typu senzoru."""
    if peripheral_id == "temperature":
        return analog_to_temperature_c(raw_value), "°C"

    if peripheral_id == "light_level":
        return analog_to_lux(raw_value), "lux"

    if peripheral_id == "humidity":
        return analog_to_humidity_percent(raw_value), "%"

    if peripheral_id == "noise":
        return analog_to_noise_db(raw_value), "dB"

    return raw_value, ""
