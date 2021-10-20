#include <Arduino.h>
#include <ArduinoJson.h>
#include <Ethernet.h>
#include <HTTPClient/HTTPClient.h>
#include <Configuration/LoadConfiguration.h>
#include <Dns.h>
#include <vector>

int HTTPClient::init()
{
    config.init();
    Serial.println("Setting up Ethernet:");
    Serial.println("\t-> Initializing the Ethernet shield to use the provided MAC address");
    Serial.println("\t   and retreving network configuration parameters through DHCP.");
    ethernetInitialized = initEthernet(Ethernet.begin(&(config.mac[0])));
    return ethernetInitialized;
}

bool HTTPClient::connect(bool retry)
{
    if (ethernetInitialized)
    {
        request = {"POST", "/sss3/register", config.config};
        unsigned long lastAttempt = millis();
        const unsigned long retryInterval = 60 * 1000;
        bool submitted = tryToConnect(config.config["serverAddress"], &lastAttempt);
        while (!submitted)
        {
            if (millis() - lastAttempt > retryInterval)
            {
                submitted = tryToConnect(config.config["serverAddress"], &lastAttempt);
            }
        }
        return write(request, &response, retry);
    }
    else
    {
        Serial.println("Cannot connect to server until HTTPClient has been initialized.");
        return false;
    }
}

bool HTTPClient::read(struct Request *req)
{
    if (server.available())
    {
        Ethernet.maintain(); //Keep current address assigned by DHCP server. Not sure how often to call this.
        req->raw = server.readString((size_t) 4096);
        if ((req->raw).length() > 0 && parseRequest(req))
        {
            Serial.print("New command from: ");
            Serial.println(server.remoteIP());
            Serial.println(req->raw);
            return true;
        }
        Serial.println(req->error);
    }
    else if (!server.connected() && !serverUnreachable)
    {
        Serial.println("Lost connection to the Control Server. Trying to re-connect...");
        connect();
    }
    return false;
}

bool HTTPClient::write(struct Request req, struct Response *res, bool retry)
{
    Ethernet.maintain();
    if (server.connected())
    {
        String message = req.method + " " + req.uri + " HTTP/1.1\r\n";
        message += "Connection: keep-alive\r\n";
        if (!req.data.isNull())
        {
            message += "Content-Type: application/json\r\n";
            message += "\r\n";
            String data;
            serializeJson(req.data, data);
            message += data;
        }
        else
        {
            message += "\r\n";
        }
        server.write(message.c_str());
        server.flush();
        return getResponse(req, res, retry);
    }
    else if (retry)
    {
        Serial.println("Lost connection to the Control Server. Trying to re-connect...");
        if (connect(false))
        {
            Serial.println("Successfully reconnected and re-registered with the server.");
            Serial.println("Attempting to send message again.");
            return write(req, res, false);
        }
        else
        {
            Serial.println("Could not re-connect to the Control Server.");
            return false;
        }
    }
    else
    {
        serverUnreachable = true;
        return false;
    }
}

int HTTPClient::initEthernet(int success)
{
    if (success) // Ethernet begin returns 0 when successful
    {
        checkHardware();
        Serial.println("\t***Successfully configured Ethernet using DHCP.***");
        Serial.println();
        Serial.println("Network Configuration:");
        Serial.print("\tHostname: ");
        Serial.print("WIZnet");
        Serial.print(config.mac[3], HEX);
        Serial.print(config.mac[4], HEX);
        Serial.println(config.mac[5], HEX);
        Serial.print("\tIP Address: ");
        Serial.println(Ethernet.localIP());
        Serial.print("\tNetmask: ");
        Serial.println(Ethernet.subnetMask());
        Serial.print("\tGateway IP: ");
        Serial.println(Ethernet.gatewayIP());
        Serial.print("\tDNS Server IP: ");
        Serial.println(Ethernet.dnsServerIP());
    }
    else
    {
        checkHardware();
        Serial.println("\t***Failed to configure Ethernet using DHCP***");
    }
    return success;
}

void HTTPClient::checkHardware()
{
    Serial.println("\t\t-> Checking for valid Ethernet shield.");
    if (Ethernet.hardwareStatus() == EthernetNoHardware)
    {
        Serial.println("\t\t***Failed to find valid Ethernet shield.***");
    }
    else
    {
        Serial.println("\t\t***Valid Ethernet shield was detected.***");
    }
    checkLink();
}

void HTTPClient::checkLink()
{
    Serial.println("\t\t-> Checking if Ethernet cable is connected.");
    if (Ethernet.linkStatus() == LinkOFF)
    {
        Serial.println("\t\t***Ethernet cable is not connected or the WIZnet chip was not");
        Serial.println("\t\t   able to establish a link with the router or switch.***");
    }
    else
    {
        Serial.println("\t\t***Ethernet cable is connected and a valid link was established.***");
    }
}

bool HTTPClient::tryToConnect(const char *serverAddress, unsigned long *lastAttempt)
{
    Serial.print("Connecting to the Control Server at ");
    Serial.print(serverAddress);
    Serial.print("... ");
    if (server.connect(serverAddress, 80))
    {
        Serial.println("connected.");
        return true;
    }
    else
    {
        *lastAttempt = millis();
        Serial.println("connection failed.");
        Serial.println("Retrying in 60 seconds.");
        Serial.println();
        return false;
    }
}

bool HTTPClient::getResponse(struct Request req, struct Response *res, bool retry)
{
    if (!waitForResponse()) return false;
    Serial.println("Server replied to request. Reading response.");
    res->raw = server.readString((size_t) 4096);
    bool didResponseParse = parseResponse(res);
    if (!didResponseParse && retry)
    {
        Serial.println("Received a poorly formatted response. Retrying.");
        return write(req, res, false);
    }
    else if (didResponseParse && !(res->code >= 200 && res->code < 400) && retry)
    {
        Serial.println("Received a bad response code. Retrying in case message got corrupted.");
        return write(req, res, false);
    }
    else
    {
        return didResponseParse;
    }
}

bool HTTPClient::waitForResponse()
{
    unsigned long originalTime = millis();
    int count = 0;
    while (!server.available())
    {
        if (millis() - originalTime >= (uint32_t) 500)
        {
            count += 1;
            originalTime = millis();
            Serial.println("Waiting on server to reply to request.");
        }
        else if (count > 10)
        {
            Serial.println("No response heard for 5 seconds.");
            return false;
        }
    }
    return true;
}

bool HTTPClient::parseResponse(struct Response *res)
{
    if (res->raw.length() <= 0) return false;
    std::array<String, 2> messageSplit = splitMessage(res->raw);
    std::vector<String> responseArray = tokenizeHTTPMessage(messageSplit[0]);
    if (responseArray.size() < 2)
    {
        res->error = "Response is incorrectly formatted";
        return false;
    }
    else if (responseArray[0] != "HTTP/1.1")
    {
        res->error = "Response is missing HTTP/1.1";
        return false;
    }
    res->code = responseArray[1].toInt();
    if (res->code == 0) {
        res->error = "Response error code could not be convert to a long";
        return false;
    }
    if (responseArray.size() >= 3) res->reason = responseArray[2];
    if (messageSplit[1].length() > 0) res->data = messageSplit[1];
    return true;
}

bool HTTPClient::parseRequest(struct Request *req)
{
    if (req->raw.length() <= 0) return false;
    std::array<String, 2> messageSplit = splitMessage(req->raw);
    std::vector<String> requestArray = tokenizeHTTPMessage(messageSplit[0]);
    if (requestArray.size() < 3)
    {
        req->error = "Request is incorrectly formatted";
        return false;
    }
    else if (requestArray[2] != "HTTP/1.1")
    {
        req->error = "Request is missing HTTP/1.1";
        return false;
    }
    req->method = requestArray[0];
    if (messageSplit[1].length() > 3)
    {
        DynamicJsonDocument data(1024);
        DeserializationError error = deserializeJson(data, messageSplit[1]);
        if (error)
        {
            req->error = "Deserializing the request data failed with code ";
            req->error += error.c_str();
            return false;
        }
        req->data = data;
    }
    return validateJSON(req);
}

bool HTTPClient::validateJSON(struct Request *req)
{
    bool containsIP = req->data.containsKey("IP");
    bool containsCAN_PORT = req->data.containsKey("CAN_PORT");
    bool containsCARLA_PORT = req->data.containsKey("CARLA_PORT");
    bool isPOST = req->method.equalsIgnoreCase("POST");
    if (!containsIP && !containsCAN_PORT && !containsCARLA_PORT && !isPOST)
    {
        return true;
    }
    else if (!containsIP || !containsCAN_PORT || !containsCARLA_PORT)
    {
        req->error = "Request JSON is missing one of the required keys.";
        return false;
    }
    String IP = req->data["IP"];
    if (!IP.startsWith("239.255."))
    {
        req->error = "IP in request JSON does not start with 239.255.";
        return false;
    }
    else if (req->data["CAN_PORT"] < 1025 || req->data["CAN_PORT"] > 65535)
    {
        req->error = "CAN port in request is out of range.";
        return false;
    }
    else if (req->data["CARLA_PORT"] < 1025 || req->data["CARLA_PORT"] > 65535)
    {
        req->error = "CARLA port in request is out of range.";
        return false;
    }
    return true;
}

std::array<String, 2> HTTPClient::splitMessage(String message)
{
    std::array<String, 2> messageSplit;
    int startOfData = message.indexOf("\r\n\r\n");
    if (startOfData == -1)
    {
        startOfData = message.indexOf("\n\n");
        if (startOfData == -1)
        {
            messageSplit[0] = message;
            messageSplit[1] = "";
            return messageSplit;
        }
    }
    messageSplit[0] = message.substring(0, startOfData);
    if (startOfData < (signed) message.length() - 1)
    {
        messageSplit[1] = message.substring(startOfData + 1);
    }
    else
    {
        messageSplit[1] = "";
    }
    return messageSplit;
}

std::vector<String> HTTPClient::tokenizeHTTPMessage(String message)
{
    char message_c_str[message.length()];
    message.toCharArray(message_c_str, message.length());
    char *tokenized;
    tokenized = strtok(message_c_str, " \r\n");
    std::vector<String> messageArray;
    while (tokenized != NULL)
    {
        String token = tokenized;
        messageArray.push_back(token);
        tokenized = strtok(NULL, " \r\n");
    }
    return messageArray;
}