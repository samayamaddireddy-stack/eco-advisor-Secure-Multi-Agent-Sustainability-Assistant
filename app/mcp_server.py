import os
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("Eco Advisor Tools")

@mcp.tool()
def get_recycling_rules(item: str, zip_code: str) -> str:
    """Get local recycling guidelines and rules for a specific item and zip code.
    
    Args:
        item: The name of the item to recycle (e.g. plastic, batteries, organic waste, paper, electronics, glass).
        zip_code: The 5-digit zip code to look up local rules for.
    """
    item_lower = item.lower()
    
    rules = {
        "plastic": "Plastics with resin codes #1 and #2 can be placed in standard curbside blue bins. Wash first. Resin codes #3-#7 must be taken to specialized sorting facilities.",
        "batteries": "Do NOT place batteries in curbside recycling bins (fire hazard). Must be dropped off at household hazardous waste collections or participating retail outlets.",
        "organic waste": "Organic waste (food scraps, yard trimmings) should be composted. Place in the green organics bin if your municipality supports compost pickup.",
        "paper": "Clean paper, cardboard, and newspaper are fully recyclable. Place in blue recycling bins. Avoid recycling greasy pizza boxes or wax-coated paper.",
        "electronics": "Electronics (e-waste) contain toxic heavy metals. Recycle them at local e-waste drop-off events or authorized electronics retailers.",
        "glass": "Glass bottles and jars are 100% recyclable. Rinse and place in curbside glass bins. Do not mix with window glass, mirrors, or ceramics."
    }
    
    for key, rule in rules.items():
        if key in item_lower:
            return f"Recycling rules in ZIP {zip_code} for {item}: {rule}"
            
    return f"Recycling rules in ZIP {zip_code} for {item}: Curbside recycling rules vary. General rule: clean and dry paper, cardboard, metal cans, and plastics #1/#2 are usually accepted in curbside bins."

@mcp.tool()
def estimate_appliance_emissions(appliance: str, hours: float) -> str:
    """Estimate the CO2 emissions (in kg) for running a home appliance for a given duration.
    
    Args:
        appliance: The name of the appliance (e.g. clothes dryer, refrigerator, laptop, air conditioner, electric oven).
        hours: Number of hours the appliance is running.
    """
    appliance_lower = appliance.lower()
    
    wattages = {
        "dryer": 3.0,
        "clothes dryer": 3.0,
        "refrigerator": 0.15,
        "fridge": 0.15,
        "laptop": 0.05,
        "computer": 0.1,
        "air conditioner": 1.5,
        "ac": 1.5,
        "oven": 2.0,
        "electric oven": 2.0,
        "television": 0.1,
        "tv": 0.1,
        "dishwasher": 1.2
    }
    
    kw = 0.5
    matched = "unknown appliance"
    for key, val in wattages.items():
        if key in appliance_lower:
            kw = val
            matched = key
            break
            
    intensity = 0.38
    kwh = kw * hours
    emissions = kwh * intensity
    
    return f"Running a {matched} ({kw} kW) for {hours} hours consumes {kwh:.2f} kWh and emits approximately {emissions:.2f} kg of CO2 (assuming standard average grid intensity)."

@mcp.tool()
def find_green_events(zip_code: str) -> str:
    """Find upcoming community environmental events, cleanups, and green workshops.
    
    Args:
        zip_code: The 5-digit zip code to locate events.
    """
    events = [
        {"name": "Community Park Cleanup & Planting", "date": "Next Saturday at 9:00 AM", "location": f"Central Park in ZIP {zip_code}"},
        {"name": "Home Energy Efficiency & Solar Workshop", "date": "July 18th at 6:30 PM", "location": f"Local Library in ZIP {zip_code}"},
        {"name": "Electronics Recycling & Hazardous Waste Drop-off", "date": "July 25th, 8:00 AM - 1:00 PM", "location": f"Municipal Center near ZIP {zip_code}"}
    ]
    
    res = f"Upcoming Eco/Green Events near ZIP {zip_code}:\n"
    for ev in events:
        res += f"- {ev['name']}: {ev['date']} at {ev['location']}\n"
    return res

if __name__ == "__main__":
    mcp.run()
