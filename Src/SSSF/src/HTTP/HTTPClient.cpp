#include <Arduino.h>
#include <CANNode/CANNode.h>
#include <ArduinoJson.h>
#include <Ethernet.h>
#include <HTTP/HTTPClient.h>
#include <Configuration/Load.h>
#include <Dns.h>
#include <vector>
#include <ArduinoHttpClient.h>
#include <TeensyID.h>

HTTPClient::HTTPClient(DynamicJsonDocument _attachedDevice, const char* _serverAddress, uint16_t _serverPort):
    CANNode(),
    client(clientSock, _serverAddress, _serverPort),
    attachedDevices(_attachedDevice),
    serverAddress(_serverAddress),
    serverIP(),
    serverPort(_serverPort),
    connectionStatus(Disconnected)
    {};

HTTPClient::HTTPClient(DynamicJsonDocument _attachedDevice, String _serverAddress, uint16_t _serverPort):
    HTTPClient(_attachedDevice, _serverAddress.c_str(), _serverPort)
    {};

HTTPClient::HTTPClient(DynamicJsonDocument _attachedDevice, IPAddress _serverIP, uint16_t _serverPort):
    CANNode(),
    client(clientSock, _serverIP, _serverPort),
    attachedDevices(_attachedDevice),
    serverAddress(NULL),
    serverIP(_serverIP),
    serverPort(_serverPort),
    connectionStatus(Disconnected)
    {};

bool HTTPClient::connect()
{
    unsigned long lastAttempt = millis();
    const unsigned long retryInterval = 60 * 1000;
    client.connectionKeepAlive();
    client.setHttpResponseTimeout(3000);
    if (registration.length() == 0) createRegistration();
    connectionStatus = attemptConnection();
    while (connectionStatus != Connected)
    {
        if (millis() - lastAttempt > retryInterval)
        {
            connectionStatus = attemptConnection();
            if (connectionStatus == Disconnected)
            {
                lastAttempt = millis();
            }
            else if (connectionStatus == Unreachable)
            {
                return false;
            }
        }
    }
    return true;
}

bool HTTPClient::read(struct Request *request, bool respondOnError)
{
    if (client.available())
    {
        request->raw = clientSock.readString((size_t) 4096);
        if (parseRequest(request))
        {
            Log.noticeln(
                "New command from: %p\n%s",
                clientSock.remoteIP(),
                request->raw.c_str()
                );
            return true;
        }
        else if (respondOnError)
        {
            struct Response response = {400, "BAD REQUEST"};
            write(&response);
        }
    }
    else if (!client.connected() && (connectionStatus != Unreachable))
    {
        Log.errorln("Lost connection to the server. Trying to re-connect...");
        connect();
    }
    return false;
}

bool HTTPClient::write(struct Response *res)
{
    if (clientSock.connected())
    {
        String msg = String(res->code) + " " + res->reason + " HTTP/1.1\r\n";
        msg += "Connection: keep-alive\r\n";
        clientSock.write(msg.c_str());
        clientSock.flush();
        return true;
    }
    else if (connectionStatus != Unreachable)
    {
        Log.errorln("Lost connection to the Server. Trying to re-connect...");
        connect();
    }
    return false;
}

int HTTPClient::write(struct Request *req, struct Response *res)
{
    if (client.connected())
    {
        String contentType;
        String content;
        int contentLength = -1;
        if (!req->json.isNull())
        {
            contentType = "application/json\r\n";
            serializeJson(req->json, content);
            contentLength = content.length();
        }
        int code = client.startRequest(
            req->uri.c_str(),
            req->method.toUpperCase().c_str(),
            contentType.c_str(),
            contentLength,
            (const byte*)content.c_str()
            );
        if (code == 0)
        {
            res->code = client.responseStatusCode();
            String data = client.responseBody();
            if (data.length() > 0)
            {
                DeserializationError e = deserializeJson(res->json, data);
                if (e)
                {
                    Log.errorln("Deserializing the response data failed.");
                    Log.errorln("Code: %s", e.c_str());
                    return -4;
                }
            }
        }
        return code;
    }
    else if (connectionStatus != Unreachable)
    {
        Log.errorln("Lost connection to the Server. Trying to re-connect...");
        connect();
    }
    return false;
}

void HTTPClient::createRegistration()
{
    DynamicJsonDocument reg(1024);
    reg["MAC"] = teensyMAC();
    reg["AttachedDevices"] = attachedDevices;
    serializeJson(reg, registration);
    
    String pretty_reg;
    serializeJsonPretty(reg, pretty_reg);
    Log.noticeln("Creating registration:\n%s", pretty_reg.c_str());
}

int HTTPClient::attemptConnection(bool retry)
{
    if (serverAddress)
    {
        Log.noticeln("Connecting to and registering with %s.", serverAddress);
    }
    else
    {
        Log.noticeln("Connecting to and registering with %p.", serverIP);
    }
    int code = client.post("/sssf/register", "application/json", registration);
    int statusCode = client.responseStatusCode();
    if (code == 0)
    {
        String response = client.responseBody();  //Must be called after responseStatusCode
        return connectionSuccessful(statusCode, retry);
    }
    else
    {
        return connectionFailed(code, retry);
    }
}

int HTTPClient::connectionSuccessful(int statusCode, bool retry)
{
    if ((statusCode >= 200) && (statusCode < 400))
    {
        return Connected;
    }
    else
    {
        Log.errorln("Received a bad status code.");
        return retry ? attemptConnection(false) : Unreachable;
    }
}

int HTTPClient::connectionFailed(int code, bool retry)
{
    if ((code == -1) || (code == -3))
    {
        Log.errorln("Connection failed. Retrying in 60 seconds." CR);
        return Disconnected;
    }
    else if (code == -4)
    {
        Log.errorln("Server returned an invalid response." CR);
        return retry ? attemptConnection(false) : Unreachable;
    }
    else
    {
        Log.errorln("Connection failed due to improper use of HTTP library." CR);
        return retry ? attemptConnection(false) : Unreachable;
    }
}

bool HTTPClient::parseRequest(struct Request *req)
{
    int endOfHeaders = req->raw.indexOf("\r\n\r\n");
    if (endOfHeaders == -1 || endOfHeaders == 0)
    {
        endOfHeaders = req->raw.indexOf("\n\n");
        if (endOfHeaders == -1 || endOfHeaders == 0)
            return false;
    }
    if (parseHeaders(endOfHeaders, req) && parseData(endOfHeaders+4, req))
    {
        return validateRequestData(req);
    }
    else
    {
        return false;
    }
}

bool HTTPClient::parseHeaders(int endOfHeaders, struct Request *req)
{
    String headers = req->raw.substring(0, endOfHeaders);
    String params[3];
    if (tokenizeRequestLine(headers, params) && params[2] == "HTTP/1.1")
    {
        req->method = params[0];
        req->uri = params[1];
        return true;
    }
    else
    {
        Log.errorln("Request line is incorrectly formatted.");
        return false;
    }
}

bool HTTPClient::parseData(int startOfData, struct Request *req)
{
    if (startOfData != ((signed) req->raw.length()))
    {
        String data = req->raw.substring(startOfData);
        DeserializationError error = deserializeJson(req->json, data);
        if (error)
        {
            Log.errorln("Deserializing the request data failed.");
            Log.errorln("Code: %s", error.c_str());
            return false;
        }
    }
    return true;
}

bool HTTPClient::validateRequestData(struct Request *req)
{
    bool id = req->json.containsKey("ID");
    bool index = req->json.containsKey("Index");
    bool ip = req->json.containsKey("IP");
    bool port = req->json.containsKey("Port");
    bool devices = req->json.containsKey("Devices");
    if (req->method.equalsIgnoreCase("POST"))
    {
        if (!ip || !port || !id || !index || !devices)
        {
            Log.errorln("Request JSON is missing 1+ required keys.");
            return false;
        }
        String IP = req->json["IP"];
        if (!IP.startsWith("239.255."))
        {
            Log.errorln("Error in the provided multicast IP.");
            return false;
        }
        else if (req->json["Port"] < 1025 || req->json["Port"] > 65535)
        {
            Log.errorln("CAN port in request is out of range.");
            return false;
        }
    }
    else if (req->method.equalsIgnoreCase("DELETE"))
    {
        if (!req->json.isNull())
        {
            Log.errorln("DELETE method cannot contain data.");
            return false;
        }
    }
    return true;
}

bool HTTPClient::tokenizeRequestLine(String headers, String params[3])
{
    int count = 0;
    char headers_c_str[headers.length()];
    headers.toCharArray(headers_c_str, headers.length());
    char *tokenized = strtok(headers_c_str, " \r\n");
    while ((tokenized != NULL) && (count < 3))
    {
        params[count] = String(tokenized);
        tokenized = strtok(NULL, " \r\n");
        count++;
    }
    return (count == 3) ? true : false;
}