import time
import random
import requests

SERVER = "http://127.0.0.1:5000"
DEVICE_ID = "esp2"
HOME_ID = 2

IP = "10.0.0.9"
ROOM = "kotelna"
BOARD = "esp32"


def heartbeat():
    requests.post(
        f"{SERVER}/api/heartbeat",
        json={
            "id": DEVICE_ID,
            "home_id": HOME_ID,
            "ip": IP,
            "room": ROOM,
            "board": BOARD
        },
        timeout=2
    )


def push_values():
    values = {
        "34": random.randint(0, 1023),
        "13": random.randint(0, 1),
        "35": random.randint(0, 1023),
        "12": random.randint(0, 1)
    }

    requests.post(
        f"{SERVER}/api/push_values",
        json={
            "id": DEVICE_ID,
            "values": values
        },
        timeout=2
    )


def pull_desired_and_apply():
    response = requests.get(
        f"{SERVER}/api/pull_desired/{DEVICE_ID}",
        timeout=2
    ).json()

    if response.get("desired"):
        print("[esp2] desired outputs:", response["desired"])


if __name__ == "__main__":
    while True:
        try:
            heartbeat()
            push_values()
            pull_desired_and_apply()
        except Exception as e:
            print("[esp2] ERR:", e)

        time.sleep(5)
