from aiohttp import web
import pint
import yaml
import paho.mqtt.client as mqtt
import json
import argparse
import time

# Initialize a unit registry for handling unit conversions
ureg = pint.UnitRegistry()

# Define mappings for imperial unit conversions
imperial_units = {"km": "mi", "°C": "°F", "km/h": "mph", "m": "ft"}

# Define a dictionary to prettify unit representations
pretty_pint = {
    "degC": "°C",
    "degF": "°F",
    "mile / hour": "mph",
    "kilometer / hour": "km/h",
    "mile": "mi",
    "kilometer": "km",
    "meter": "m",
    "foot": "ft",
}

# Define assumed units for specific sensor readings
assumed_units = {
    "04": "%",
    "05": "°C",
    "0c": "rpm",
    "0d": "km/h",
    "0f": "°C",
    "11": "%",
    "1f": "km",
    "21": "km",
    "2f": "%",
    "31": "km",
}

# Define mappings for short and full sensor names
assumed_short_name = {
    "04": "engine_load",
    "05": "coolant_temp",
    "0c": "engine_rpm",
    "0d": "speed",
    "0f": "intake_temp",
    "11": "throttle_pos",
    "1f": "run_since_start",
    "21": "dis_mil_on",
    "2f": "fuel",
    "31": "dis_mil_off",
}

assumed_full_name = {
    "04": "Engine Load",
    "05": "Coolant Temperature",
    "0c": "Engine RPM",
    "0d": "Vehicle Speed",
    "0f": "Intake Air Temperature",
    "11": "Throttle Position",
    "1f": "Distance Since Engine Start",
    "21": "Distance with MIL on",
    "2f": "Fuel Level",
    "31": "Distance with MIL off",
}

# Global dictionary to store parsed session data
data = {}

def pretty_units(unit):
    """Converts standard unit representation to a more readable format."""
    return pretty_pint.get(unit, unit)

def unpretty_units(unit):
    """Converts prettified unit representation back to standard format."""
    return next((pint_unit for pint_unit, pretty_unit in pretty_pint.items() if pretty_unit == unit), unit)

def convert_units(value, u_in, u_out):
    """Converts a value from one unit to another."""
    q_in = ureg.Quantity(value, u_in)
    q_out = q_in.to(u_out)
    return {"value": round(q_out.magnitude, 2), "unit": str(q_out.units)}

def pretty_convert_units(value, u_in, u_out):
    """Converts units and returns a prettified result."""
    p_in, p_out = unpretty_units(u_in), unpretty_units(u_out)
    res = convert_units(value, p_in, p_out)
    return {"value": res["value"], "unit": pretty_units(res["unit"])}

async def process_torque(request):
    """Handles incoming HTTP requests, processes data, and publishes to MQTT."""
    session = parse_fields(request.query)
    publish_data(session)
    return web.Response(text="OK!")

def parse_fields(qdata):
    """Parses incoming query data and stores it in the session dictionary."""
    session = qdata.get("session")
    if session is None:
        raise Exception("No Session")
    
    # Initialize session if not already present
    data.setdefault(session, {
        "profile": {},
        "unit": {},
        "defaultUnit": {},
        "fullName": {},
        "shortName": {},
        "value": {},
        "unknown": [],
        "time": 0,
    })

    # Process query data
    for key, value in qdata.items():
        if key.startswith("userUnit"):
            continue
        
        prefixes = {
            "userShortName": ("shortName", 13),
            "userFullName": ("fullName", 12),
            "defaultUnit": ("defaultUnit", 11),
            "k": ("value", 1),
            "profile": ("profile", 7)
        }
        
        for prefix, (target, offset) in prefixes.items():
            if key.startswith(prefix):
                item = key[offset:]
                if prefix == "k" and len(item) == 1:
                    item = "0" + item
                data[session][target][item] = value
                break
        else:
            if key in {"eml", "time", "v", "session", "id"}:
                profile_keys = {"eml": "email", "v": "version", "id": "id"}
                data[session]["profile"].setdefault(profile_keys.get(key, key), value)
            else:
                data[session]["unknown"].append({"key": key, "value": value})
    
    return session

def publish_data(session):
    """Publishes parsed data to MQTT."""
    mqttc.publish(get_topic_prefix(session), json.dumps(get_data(session)))

def mqttc_create():
    """Creates and configures the MQTT client."""
    global mqttc, mqttc_time
    mqttc = mqtt.Client(client_id="torque", clean_session=True)
    mqttc.username_pw_set(username=config["mqtt"].get("username"), password=config["mqtt"].get("password"))
    mqttc.connect(config["mqtt"]["host"], config["mqtt"].get("port", 1883), keepalive=60)
    mqttc.loop_start()
    mqttc_time = time.time()

# Load configuration
args = argparse.ArgumentParser().add_argument("-c", "--config", required=True, help="Directory holding config.yaml").parse_args()
with open(args.config.rstrip("/") + "/config.yaml") as file:
    config = yaml.load(file, Loader=yaml.FullLoader)

mqttc_create()

# Start the web server
if __name__ == "__main__":
    web.run_app(web.Application().router.add_get("/", process_torque), host=config.get("server", {}).get("ip", "0.0.0.0"), port=config.get("server", {}).get("port", 5000))
