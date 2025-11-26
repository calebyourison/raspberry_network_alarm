import requests
import RPi.GPIO as GPIO
import time
from typing import Literal
import logging

# Set Variables

# URLs

# ALL urls must fail to trigger a trouble. Fewer urls results in a faster overall process but might create false positives.
internet_urls: list[str] = [
    "https://www.google.com",
    "https://www.cloudflare.com"
]

# If set, system will send a heartbeat to a local uptime-kuma push device to check network_alarm uptime
uptime_kuma_push_url: str|None = None

# Intervals

# Frequency to check websites
internet_check_interval: int = 60
# Number of outages to trigger a reset/extended trouble
reset_output_threshold: int = 10
# Number of seconds to trigger a reset prior to restore
reset_output_trigger_time: int = 15

# Pins
# Add or modify as needed
# Additional pins should be added to appropriate groups

green_yellow_led: tuple[str, int] = ("Green/Yellow LED", 17)
red_led: tuple[str, int] = ("Red LED", 27)
trouble_zone: tuple[str, int] = ("Trouble Supervisory Zone", 22)
reset_output: tuple[str, int] = ("Reset Output", 23)

# Groups
# Triggered on a single failed request
trouble_pins: list[tuple[str, int]] = [green_yellow_led, trouble_zone]
# Triggered after reaching the reset_output_threshold
extended_trouble_pins: list[tuple[str, int]] = [red_led]
# Triggered for the reset_output_trigger_time every multiple of the reset_output_threshold
reset_pins: list[tuple[str, int]] = [reset_output]

all_pins: list[tuple[str, int]] = trouble_pins + extended_trouble_pins + reset_pins

# Optional verbose output
VERBOSE = False

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if VERBOSE else logging.WARNING)

logging.basicConfig(
    level=logger.level,
    format="%(levelname)s: %(message)s"
)

# Running outage count
outage_count = 0


def setup_pins(pins: list[tuple[str, int]]) -> None:
    """Set pins to output mode"""

    GPIO.setmode(GPIO.BCM)
    logger.debug("Set Mode BCM pin numbering")

    for (name, pin_number) in pins:
        GPIO.setup(pin_number, GPIO.OUT)
        present_state = GPIO.input(pin_number)

        logger.debug(f"{name} ({pin_number}) status: {present_state}")


def change_pin_state(pin: tuple[str, int], command: Literal["On", "Off"]) -> None:
    """Change the state of a given pin and logger.debug its status"""
    pin_name, pin_number = pin

    if command == "On":
        GPIO.output(pin_number, GPIO.HIGH)
    elif command == "Off":
        GPIO.output(pin_number, GPIO.LOW)
    else:
        logger.debug("Improper command")

    pin_status = GPIO.input(pin_number)

    logger.debug(f"{pin_name} ({pin_number}) status: {pin_status}")


def check_internet(urls:list[str], timeout:int=3) -> bool:
    """Check every url in list until one is reachable (True), otherwise return False"""

    for url in urls:
        try:
            response = requests.get(url=url, timeout=timeout)
            if response.status_code == 200:
                return True
        except Exception as e:
            logger.debug(e)
            continue
    return False

def normal_status(uptime_kuma_url:str|None, pins:list[tuple[str, int]]) -> None:
    """If internet connection online, reset all pins, outage count, push to local uptime-kuma"""
    global outage_count

    outage_count = 0

    logger.debug("Set all pins to Off")
    for pin in pins:
        change_pin_state(pin, command="Off")

    if uptime_kuma_url:
        try:
            resp = requests.get(url=uptime_kuma_url)
            logger.debug(f"Internet Check OK, pushing to Uptime-Kuma {resp}")

        except Exception as e:
            logger.debug(f"Cannot push to Uptime-Kuma: {e}")


def trouble_status(troubles: list[tuple[str, int]], extended_troubles: list[tuple[str, int]], resets: list[tuple[str, int]]) -> None:
    """If internet connection fails, perform appropriate actions"""

    global outage_count

    outage_count += 1
    logger.debug(f"Internet Outage. Running count: {outage_count}")

    # Trigger trouble pins
    for pin in troubles:
        change_pin_state(pin=pin, command="On")

    # At threshold trigger extended trouble pins
    if outage_count >= reset_output_threshold:
        for pin in extended_troubles:
            change_pin_state(pin=pin, command="On")

        # Short trigger and restore of the reset pins on every multiple of the threshold
        # ie trigger for 15 seconds every 10 failures
        if outage_count % reset_output_threshold == 0:
            for pin in resets:
                change_pin_state(pin, command="On")

            logger.debug(f"Waiting {reset_output_trigger_time} seconds")
            time.sleep(reset_output_trigger_time)

            for pin in resets:
                change_pin_state(pin, command="Off")


def run() -> None:
    """Main program sequence"""

    internet_status = check_internet(urls=internet_urls)

    if internet_status:
        normal_status(uptime_kuma_url=uptime_kuma_push_url, pins=all_pins)

    else:
        trouble_status(troubles=trouble_pins, extended_troubles=extended_trouble_pins, resets=reset_pins)



def main() -> None:
    logger.debug("Running")

    try:
        setup_pins(pins=all_pins)

        while True:
            run()

            time.sleep(internet_check_interval)

    except KeyboardInterrupt:
        logger.debug("Exiting Network Alarm...")
    finally:
        GPIO.cleanup()
        pass

if __name__ == "__main__":
    main()