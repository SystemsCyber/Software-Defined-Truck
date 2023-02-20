import numpy as np
import matplotlib.pyplot as plt
import random
import multiprocessing

def exponential_moving_average(points, alpha=0.1):
    alpha = 2 / (len(points) + 1)
    # initialize the moving average
    moving_average = [points[0]]

    # loop through the points and calculate the moving average
    for i in range(1, len(points)):
        moving_average.append(alpha * points[i] + (1 - alpha) * moving_average[i - 1])

    return moving_average

# def exponential_moving_average(values, period):
#         k = 2 / (period + 1)
#         val = values[8 - period]
#         if period == 1:
#             return val
#         res = (val * k) + (exponential_moving_average(values, period - 1) * (1 - k))
#         return res

def receive_points(pipe):
    # receive the first 8 points
    points = [pipe.recv() for i in range(8)]

    # loop through the remaining points
    for i in range(8, 100):
        # receive a new point
        point = pipe.recv()

        # add the new point to the list of points
        points.append(point)

        # calculate the moving average
        moving_average = exponential_moving_average(points[i-7:i+1])

        # send the moving average back to the parent process
        pipe.send(moving_average[-1])
        # pipe.send(moving_average)

def main():
    # generate a list of 100 points of a sine wave
    x = np.linspace(0, 10, 100)
    y = np.sin(x)

    # add random noise to each point
    y_noisy = [y[i] + random.uniform(-1, 1) for i in range(100)]

    # create a pipe for interprocess communication
    parent_pipe, child_pipe = multiprocessing.Pipe()

    # start the child process
    process = multiprocessing.Process(target=receive_points, args=(child_pipe,))
    process.start()

    # send the noisy points to the child process
    for point in y_noisy:
        parent_pipe.send(point)

    # receive the moving average points from the child process
    y_moving_average = [parent_pipe.recv() for i in range(92)]
    yma = y_noisy[:8] + y_moving_average

    # wait for the child process to finish
    
    process.join()
    process.close()

    # plot the original points and the moving average
    plt.plot(x, y, label="Original")
    plt.plot(x, yma, label="Moving Average")
    plt.legend()
    plt.show()

if __name__ == "__main__":
    main()
