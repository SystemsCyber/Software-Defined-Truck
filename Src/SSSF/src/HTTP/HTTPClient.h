#ifndef http_client_h_
#define http_client_h_

#include <Arduino.h>
#include <CANNode/CANNode.h>
#include <ArduinoHttpClient.h>
#include <ArduinoJson.h>
#include <IPAddress.h>
#include <Ethernet.h>
#include <Configuration/Load.h>
#include <vector>

enum ConnectionStatus
{
    Unreachable,
    Disconnected,
    Connected
};

class HTTPClient: public virtual CANNode
{
private:
    EthernetClient clientSock;
    HttpClient client;

    DynamicJsonDocument attachedDevices;
    const char *serverAddress;
    IPAddress serverIP;
    uint16_t serverPort;

    volatile int connectionStatus;

public:
    struct Request
    {
        String method;
        String uri;
        StaticJsonDocument<1024> json;
        String raw;
    };

    struct Response
    {
        uint16_t code;
        String reason;
        StaticJsonDocument<1024> json;
        String raw;
        String error;
    };

    HTTPClient(DynamicJsonDocument _attachedDevices, const char* _serverAddress, uint16_t _serverPort = 80);
    HTTPClient(DynamicJsonDocument _attachedDevices, String _serverAddress, uint16_t _serverPort = 80);
    HTTPClient(DynamicJsonDocument _attachedDevices, IPAddress _serverIP, uint16_t _serverPort = 80);
    
    virtual bool connect();
    virtual bool read(struct Request *request, bool respondOnError = true);
    virtual bool write(struct Response *response);
    virtual int write(struct Request *request, struct Response *response);

private:
    int attemptConnection(bool retry = true);
    int connectionSuccessful(int statusCode, bool retry = true);
    int connectionFailed(int code, bool retry = true);

    bool parseRequest(struct Request *req);
    bool parseHeaders(int endOfHeaders, struct Request *req);
    bool parseData(int startOfData, struct Request *req);
    bool tokenizeRequestLine(String headers, String params[3]);
    bool validateRequestData(struct Request *request);
};

#endif /* http_client_h_ */