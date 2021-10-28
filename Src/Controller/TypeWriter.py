from time import sleep
from shutil import get_terminal_size

class TypeWriter:
    bold = '\u001b[1m'
    black = '\u001b[30m'
    red = '\u001b[31m'
    green  = '\u001b[32m'
    yellow = '\u001b[33m'
    blue = '\u001b[34m'
    magenta = '\u001b[35m'
    cyan = '\u001b[36m'
    white = '\u001b[37m'
    reset = '\u001b[0m'

    @staticmethod
    def write(sentence, color=None, end='\n'):
        print(color, end='')
        for char in sentence:
            print(char, sep='', end='', flush=True)
            sleep(0.01)
        print(TypeWriter.reset, end=end)

    @staticmethod
    def bar():
        # os.system('cls' if os.name == 'nt' else 'clear')
        term_size = get_terminal_size()
        greeting_message = "* ECU Selection Menu *"
        print(f'{TypeWriter.green}{greeting_message:*^{term_size[0]-5}}{TypeWriter.reset}')