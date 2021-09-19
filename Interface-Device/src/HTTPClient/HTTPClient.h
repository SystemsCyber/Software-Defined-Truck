#ifndef http_client_h_
#define http_client_h_

#include <Arduino.h>
#include <ArduinoJson.h>
#include <IPAddress.h>
#include <Ethernet.h>
#include <Configuration/LoadConfiguration.h>
#include <vector>

class HTTPClient
{
private:
    LoadConfiguration config;  // Configuration object containing initailization values.
    IPAddress serverAddress;
    bool ethernetInitialized;

public:
    struct Request {
        String method;
        String uri;
        StaticJsonDocument<1024> data;
        String error;
        String raw;
    } request;

    struct Response {
        String version;
        long code;
        String reason;
        String data;
        String error;
        String raw;
    } response;
    EthernetClient server;      // Connection object for the server.

    HTTPClient() : ethernetInitialized(false) {};
    // Send configuration info to the server. If the connection to the server
    // fails, retry every minute and print the time to show that the program is
    // still running.
    // Returns once it has successfully send the data to the server.
    int init();
    bool connect();
    // Maintain connection and read Server Side Events if any exist.
    bool read(struct Request *req);
    // Maintain connection and write Client Side Events if any exist.
    bool write(struct Request req, struct Response *res, bool retry = true);

private:
    // Initialise the Ethernet shield to use the provided MAC address and
    // gain the rest of the configuration through DHCP.
    // Returns 0 if the DHCP configuration failed, and 1 if it succeeded.
    int initEthernet(int success);
    static void checkHardware();
    static void checkLink();

    IPAddress resolveServerAddress(const char *nameOrIP);
    bool tryToConnect(unsigned long *lastAttempt, const unsigned long retryInterval);
    bool getResponse(struct Request req, struct Response *res, bool retry = true);
    bool waitForResponse();
    bool parseResponse(struct Response *res);
    bool parseRequest(struct Request *req);
    bool validateJSON(struct Request *req);
    std::array<String, 2> splitMessage(String message);
    std::vector<String> tokenizeHTTPMessage(String message);
};

#endif /* http_client_h_ */