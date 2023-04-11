import ctypes
import random
from multiprocessing import Process, Queue
import heapq
import time

def producer(q):
    num_iterations = 100000
    max_value = 1000
    for _ in range(num_iterations):
        class RandomStruct(ctypes.Structure):
            _fields_ = [("a", ctypes.c_uint64),
                        ("b", ctypes.c_uint64),
                        ("c", ctypes.c_uint64),
                        ("d", ctypes.c_uint64)]
        
        random_struct = RandomStruct(
            random.randint(0, max_value),
            random.randint(0, max_value),
            random.randint(0, max_value),
            random.randint(0, max_value)
        )
        q.put((random_struct.a, random_struct.b, random_struct.c, random_struct.d))
    q.put(None)  # Signal the consumer that the producer is done

def consumer(q):
    frequencies = [0] * 1001
    while True:
        random_tuple = q.get()
        if random_tuple is None:
            break
        for number in random_tuple:
            frequencies[number] += 1

    top_numbers = heapq.nlargest(10, range(len(frequencies)), key=frequencies.__getitem__)
    for number in top_numbers:
        print(f"{number}: {frequencies[number]} times")

if __name__ == "__main__":
    q = Queue()
    producer_process = Process(target=producer, args=(q,))
    consumer_process = Process(target=consumer, args=(q,))
    start = time.perf_counter_ns()
    producer_process.start()
    consumer_process.start()

    producer_process.join()
    consumer_process.join()
    end = time.perf_counter_ns()
    print(f"Time taken: {(end - start) / 1000000} ms")
