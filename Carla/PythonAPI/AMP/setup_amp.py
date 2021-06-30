#!/usr/bin/env python

import os
import sys
import shutil
import wget
import time
import tempfile

anaconda_installation_path = ""
carla_installation_path = ""

class tcolors:
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


def bye():
    typewritter("Bye! Exiting...", tcolors.red)
    time.sleep(0.5)
    exit()


def typewritter(sentence, color=None, end='\n'):
    print(color, end='')
    for char in sentence:
        print(char, sep='', end='', flush=True)
        time.sleep(0.01)

    print(tcolors.reset, end=end)


def greeting_bar():
    os.system('cls' if os.name == 'nt' else 'clear')
    term_size = shutil.get_terminal_size()
    user_name = os.getlogin()
    greeting_message = "* Welcome, " + user_name + " *"
    print(f'{tcolors.green}{greeting_message:*^{term_size[0]-5}}{tcolors.reset}')


def welcome_check():
    typewritter('Proceed with setup of virtual environment for CARLA client? ', tcolors.cyan, '')
    typewritter('[', tcolors.red, '')
    typewritter('Y', tcolors.yellow, '')
    typewritter('/n] ', tcolors.red, '')
    proceed = input('').lower()
    if (proceed != 'y') and (proceed != 'n'):
        print(f'{tcolors.magenta}Please enter {tcolors.yellow}y{tcolors.magenta} or {tcolors.red}n{tcolors.magenta}.')
        welcome_check()
    elif (proceed == 'y'):
        greeting_bar()
        carla_exists()
        anaconda_exists()
    elif (proceed == 'n'):
        bye()


def carla_exists():
    typewritter('Is the latest version of CARLA downloaded and unzipped? ', tcolors.cyan, '')
    typewritter('[', tcolors.red, '')
    typewritter('Y', tcolors.yellow, '')
    typewritter('/n] ', tcolors.red, '')
    proceed = input('').lower()
    if (proceed != 'y') and (proceed != 'n'):
        print(f'{tcolors.magenta}Please enter {tcolors.yellow}y{tcolors.magenta} or {tcolors.red}n{tcolors.magenta}.')
        carla_exists()
    elif (proceed == 'y'):
        check_filepath()
    elif (proceed == 'n'):
        print()
        typewritter("Please download and unzip the latest version of CARLA before running this setup.", tcolors.cyan)
        time.sleep(1)
        bye()


def check_filepath():
    global carla_installation_path
    typewritter('Please enter the filepath to the CARLA folder: ', tcolors.cyan, '')
    proceed = input('')
    if len(proceed) < 1:
        bye()
    typewritter("Checking filepath...", tcolors.cyan, '')
    if os.path.isdir(proceed):
        carla_installation_path = proceed
        typewritter("Given filepath is ", tcolors.cyan, '')
        typewritter("valid", tcolors.green, '')
        typewritter(".", tcolors.cyan)
    elif not os.path.isdir(proceed):
        typewritter("Given filepath is ", tcolors.cyan, '')
        typewritter("not valid", tcolors.red, '')
        typewritter(".", tcolors.cyan)
        check_filepath()


def anaconda_exists():
    typewritter('Checking for anaconda installation:', tcolors.cyan)
    path = conda_path()
    folder = conda_folder()
    if path:
        if not folder:
            typewritter('Weird, but that will still work.', tcolors.cyan)
            typewritter('Concluding that Anaconda is ', tcolors.cyan, '')
            typewritter('installed.', tcolors.green)
        else:
            typewritter('Anaconda is ', tcolors.cyan, '')
            typewritter('installed.', tcolors.green)
            setting_up_carla_env()
    elif folder:
        typewritter('Anaconda is ', tcolors.cyan, '')
        typewritter('installed', tcolors.green, '')
        typewritter(' but ', tcolors.cyan, '')
        typewritter('not ', tcolors.red, '')
        typewritter('on your path.', tcolors.cyan)
        add_conda_path()
    else:
        typewritter('Anaconda is ', tcolors.cyan, '')
        typewritter('not installed', tcolors.red, '')
        typewritter('.', tcolors.cyan)
        downloading_anaconda()


def add_conda_path():
    typewritter('Add conda to the program\'s temporary path? ', tcolors.cyan, '')
    typewritter('[', tcolors.red, '')
    typewritter('Y', tcolors.yellow, '')
    typewritter('/n] ', tcolors.red, '')
    proceed = input('').lower()
    if (proceed != 'y') and (proceed != 'n'):
        print(f'{tcolors.magenta}Please enter {tcolors.yellow}y{tcolors.magenta} or {tcolors.red}n{tcolors.magenta}.')
        add_conda_path()
    elif (proceed == 'y'):
        typewritter('Adding conda to path...', tcolors.cyan)
        if os.name == 'nt':
            os.environ["PATH"] += os.pathsep + os.path.join(anaconda_installation_path)
            os.environ["PATH"] += os.pathsep + os.path.join(anaconda_installation_path, "Scripts")
            os.environ["PATH"] += os.pathsep + os.path.join(anaconda_installation_path, "Library", "bin")
        else:
            os.environ["PATH"] += os.pathsep + os.path.join(anaconda_installation_path, "bin", "conda")
        typewritter('Testing whether it worked...', tcolors.cyan)
        anaconda_exists()
    elif (proceed == 'n'):
        bye()


def conda_path():
    conda_path = shutil.which("conda")
    typewritter('\t- conda was', tcolors.cyan, '')
    if conda_path:
        typewritter(' found ', tcolors.green, '')
    else:
        typewritter(' not found ', tcolors.red, '')
    typewritter('on system path.', tcolors.cyan)
    return conda_path


def conda_folder():
    home_folder = os.path.expanduser("~")
    base_dir = os.path.splitdrive(sys.executable)[0] + os.sep
    conda_folder_system = ''
    conda_folder_home = ''
    if os.name == 'nt':
        conda_folder_system = check_folder(os.path.join(base_dir, "ProgramData"))
        conda_folder_home = check_folder(home_folder)
    else:
        conda_folder_system = check_folder(os.path.join(base_dir, "opt")) or check_folder(base_dir)
        conda_folder_home = os.path.isdir(home_folder)
    typewritter('\t- Anaconda3 folder was ', tcolors.cyan, '')
    if conda_folder_home or conda_folder_system:
        typewritter(' found.', tcolors.green)
    else:
        typewritter(' not found. ', tcolors.red)
    return conda_folder_home or conda_folder_system


def check_folder(folder):
    global anaconda_installation_path
    if os.path.isdir(os.path.join(folder, "Anaconda3")):
        anaconda_installation_path = os.path.join(folder, "Anaconda3")
        return True
    elif os.path.isdir(os.path.join(folder, "anaconda3")):
        anaconda_installation_path = os.path.isdir(os.path.join(folder, "anaconda3"))
        return True
    else:
        return False


def downloading_anaconda():
    typewritter('Install Anaconda? ', tcolors.cyan, '')
    typewritter('[', tcolors.red, '')
    typewritter('Y', tcolors.yellow, '')
    typewritter('/n] ', tcolors.red, '')
    proceed = input('').lower()
    if (proceed != 'y') and (proceed != 'n'):
        print(f'{tcolors.magenta}Please enter {tcolors.yellow}y{tcolors.magenta} or {tcolors.red}n{tcolors.magenta}.')
        downloading_anaconda()
    elif (proceed == 'y'):
        typewritter('Downloading anaconda...', tcolors.cyan)
        tdir = tempfile.mkdtemp()
        filename = ''
        if os.name == 'nt':
            filename = wget.download('https://repo.anaconda.com/archive/Anaconda3-5.3.1-Windows-x86_64.exe', out=tdir)
        else:
            filename = wget.download('https://repo.anaconda.com/archive/Anaconda3-5.3.1-Linux-x86_64.sh', out=tdir)
        launching_anaconda_installer(os.path.split(filename))
        shutil.rmtree(tdir)
    elif (proceed == 'n'):
        bye()


def launching_anaconda_installer(filepath):
    print()
    typewritter('Launching anaconda installer...', tcolors.cyan)
    typewritter('Anaconda silent installation does not return any progress indicators (▰˘︹˘▰)', tcolors.cyan)
    typewritter('Hopefully this installs in a reasonable timeframe ¯\_(ツ)_/¯', tcolors.cyan)
    time.sleep(0.5)
    if os.name == 'nt':
        os.system("start /wait \"\" " + filepath[0] + "\\Anaconda3-5.3.1-Windows-x86_64.exe /InstallationType=JustMe /AddToPath=1 /RegisterPython=0 /S /D=%UserProfile%\Anaconda3")
    else:
        os.system("bash cd " + filepath[0] + " && ~/anaconda.sh -f -p $HOME/anaconda")
    print()
    typewritter('Checking that Anaconda was setup correctly...', tcolors.cyan)
    anaconda_exists()


def setting_up_carla_env():
    create = "conda create -y -n pycarla python=3.7.9 && "
    activate = "conda activate pycarla && "
    shortcut = "conda install -y console_shortcut && "
    pipinstall = "pip install --no-input -r "
    carla_requirements = pipinstall + os.path.join(carla_installation_path, "PythonAPI", "carla", "requirements.txt") + " && "
    examples_requirements = pipinstall + os.path.join(carla_installation_path, "PythonAPI", "examples", "requirements.txt") + " && "
    util_requirements = pipinstall + os.path.join(carla_installation_path, "PythonAPI", "util", "requirements.txt")
    os.system(create + activate + shortcut + carla_requirements + examples_requirements + util_requirements)
    wrapping_up()


def wrapping_up():
    print()
    typewritter("You should now have a shortcut located in your start menu / applications menu called \"Anaconda Prompt (pycarla)\".", tcolors.cyan)
    time.sleep(1)
    typewritter("That shortcut will open a conda environment with all carla-required python dependecies installed.", tcolors.cyan)
    time.sleep(1)
    bye()


def main():
    greeting_bar()
    welcome_check()


if __name__== '__main__':
    main()