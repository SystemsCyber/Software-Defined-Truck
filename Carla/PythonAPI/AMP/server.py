from broker import Broker


def main():
    server = Broker()
    server.listen()


if __name__ == "__main__":
    main()