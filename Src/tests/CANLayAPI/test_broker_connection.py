import CANLay
import pytest

import subprocess
import threading
import queue

def reader(pipe, q):
    try:
        while True:
            line = pipe.readline()
            if line:
                q.put(line.strip())
            else:
                break
    finally:
        pipe.close()

def get_output(q):
    try:
        return q.get_nowait()
    except queue.Empty:
        return None
    
def start_server():
    global stdout_queue, stderr_queue, stdout_thread, stderr_thread
    # Replace 'your_command' with the command you want to run
    cmd = "your_command"
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)

    # Create queues for stdout and stderr
    stdout_queue = queue.Queue()
    stderr_queue = queue.Queue()

    # Start threads to read stdout and stderr
    stdout_thread = threading.Thread(target=reader, args=(process.stdout, stdout_queue))
    stderr_thread = threading.Thread(target=reader, args=(process.stderr, stderr_queue))
    stdout_thread.start()
    stderr_thread.start()

def stop_server():
    # Get the remaining output after the process has terminated
    while not stdout_queue.empty() or not stderr_queue.empty():
        stdout_output = get_output(stdout_queue)
        stderr_output = get_output(stderr_queue)

        if stdout_output:
            print(f"STDOUT: {stdout_output}")
        if stderr_output:
            print(f"STDERR: {stderr_output}")

    # Join the threads
    stdout_thread.join()
    stderr_thread.join()

def test_server():
    start_server()
    assert get_output(stderr_queue) == None
    stop_server()

def test_default_broker_args():
    start_server()
    