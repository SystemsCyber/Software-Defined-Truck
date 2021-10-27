#ifndef http_client_h_
#define http_client_h_

#include <Arduino.h>
#include <CANNode/CANNode.h>
#include <ArduinoHttpClient.h>
#include <ArduinoHttpServer.h>
#include <ArduinoJson.h>
#include <IPAddress.h>
#include <Ethernet.h>
#include <Configuration/Load.h>
#include <vector>

using ArduinoHttpServer::StreamHttpRequest;
using ArduinoHttpServer::StreamHttpReply;
using ArduinoHttpServer::StreamHttpErrorReply;
using ArduinoHttpServer::Method;

enum ConnectionStatus
{
    Unreachable,
    Disconnected,
    Connected
};

class HTTPClient: public CANNode
{
public:
    EthernetClient httpSock;

private:
    HttpClient client;
    DynamicJsonDocument attachedDevice;
    const char *serverAddress;
    IPAddress serverIP;
    uint16_t serverPort;
    volatile int connectionStatus;

protected:
    uint32_t id;

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
        String error;
        StaticJsonDocument<1024> json;
        String raw;
    };

    HTTPClient(DynamicJsonDocument _attachedDevice, const char* _serverAddress, uint16_t _serverPort = 80);
    HTTPClient(DynamicJsonDocument _attachedDevice, String _serverAddress, uint16_t _serverPort = 80);
    HTTPClient(DynamicJsonDocument _attachedDevice, IPAddress _serverIP, uint16_t _serverPort = 80);
    
    virtual bool connect();
    virtual void listen();
    virtual bool read(StreamHttpRequest<4096> *request);
    virtual bool write(StreamHttpReply *response);
    virtual int write(StreamHttpRequest<4096> *request, StreamHttpReply *response);

private:
    int attemptConnection(bool retry = true);
    int connectionSuccessful(bool retry = true);
    int connectionFailed(int code, bool retry = true);

    bool parseRequest(struct Request *req);
    bool parseHeaders(int endOfHeaders, struct Request *req);
    bool parseData(int startOfData, struct Request *req);
    bool tokenizeRequestLine(String headers, String params[3]);
    bool validateRequestData(struct Request *request);
};

#endif /* http_client_h_ */