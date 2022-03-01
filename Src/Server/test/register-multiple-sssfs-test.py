import json
from http.client import HTTPConnection
import time

def create_sssf(request):
    sssf = HTTPConnection("127.0.0.1")
    sssf.connect()
    sssf.request(
        "POST",
        "/sssf/register",
        request,
        {"Content-Type": "application/json"}
    )
    time.sleep(1)
    response = sssf.getresponse()
    length = response.length
    data = response.read(length)
    return sssf, data

def main():
    sssf1, _ = create_sssf(json.dumps({
            "MAC": "04:e9:e5:4f:2c:1f",
            "AttachedDevices": [{
	            "Type": ["ECM", "Engine Control Module"],
	            "Year": 2000,
	            "Model": "GenericModel",
	            "Make": "Cummins",
	            "SN": "1a2b3c4d"
	        }]
        }))
    sssf2, _ = create_sssf(json.dumps({
            "MAC": "04:e9:e5:78:cf:dd",
            "AttachedDevices": [{
	            "Type": ["BCU", "Brake Control Unit"],
	            "Year": 1999,
	            "Model": "GenericModel",
	            "Make": "Detroit Desiel",
	            "SN": "1a2b3c4d"
	        }]
        }))
    sssf3, _ = create_sssf(json.dumps({
            "MAC": "04:e9:e5:61:4a:e0",
            "AttachedDevices": [{
	            "Type": ["PSU", "Power Steering Unit"],
	            "Year": 2002,
	            "Model": "GenericModel",
	            "Make": "Kenworth",
	            "SN": "1a2b3c4d"
	        }]
        }))
    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            sssf1.close()
            sssf2.close()
            sssf3.close()
            break

if __name__ == "__main__":
    main()