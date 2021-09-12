#ifndef http_client_h_
#define http_client_h_

#include <Arduino.h>
#include <ArduinoJson.h>
#include <Ethernet.h>
#include <Configuration/LoadConfiguration.h>
#include <vector>

class HTTPClient
{
private:
    LoadConfiguration _config;  // Configuration object containing initailization values.

public:
    String request;             // String to hold outgoing messages.
    String requestMethod;
    DynamicJsonDocument requestData;
    String requestError;
    String response;            // String to hold incoming messages.
    long responseCode;
    String responseReason;
    String responseMessage;
    String responseError;
    EthernetClient server;      // Connection object for the server.

    HTTPClient() : requestData(96) {};
    // Send configuration info to the server. If the connection to the server
    // fails, retry every minute and print the time to show that the program is
    // still running.
    // Returns once it has successfully send the data to the server.
    int init();
    bool enlist();
    // Maintain connection and read Server Side Events if any exist.
    bool readSSE();
    // Maintain connection and write Client Side Events if any exist.
    bool writeCSE(String method, String data = "");

private:
    // Initialise the Ethernet shield to use the provided MAC address and
    // gain the rest of the configuration through DHCP.
    // Returns 0 if the DHCP configuration failed, and 1 if it succeeded.
    int initEthernet(int success);
    static void checkHardware();
    static void checkLink();
    bool submitConfiguration(unsigned long *lastAttempt);
    bool awaitConfirmation();
    bool parseResponse();
    bool parseRequest();
    bool validateJSON();
    std::vector<String> tokenizeHTTPMessage(String message);
};

#endif /* http_client_h_ */