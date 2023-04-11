import sys
from pathlib import Path
sys.path.insert(0, str(Path('../../').resolve()))
import CANLay
from time import sleep
import logging

def main():
    canlay = CANLay.CANLay(
        log_level = logging.DEBUG,
        log_type = CANLay.LOGTYPE_CONSOLE | CANLay.LOGTYPE_FILE,
        log_filename = "CANLay.log",
        log_directory_path = "./Logs"
    )
    canlay.start()
    sleep(1)
    canlay.stop()

if __name__ == "__main__":
    main()