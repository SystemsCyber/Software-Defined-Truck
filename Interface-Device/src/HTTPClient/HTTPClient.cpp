#include <Arduino.h>
#include <ArduinoJson.h>
#include <Ethernet.h>
#include <HTTPClient/HTTPClient.h>
#include <Configuration/LoadConfiguration.h>
#include <Dns.h>
#include <vector>

int HTTPClient::init()
{
    Serial.println("Setting up Ethernet:");
    Serial.println("\t-> Initializing the Ethernet shield to use the provided MAC address");
    Serial.println("\t   and retreving network configuration parameters through DHCP.");
    return initEthernet(Ethernet.begin(&(_config.mac[0])));
}

bool HTTPClient::enlist()
{
    if (!(_config.FQDN[0] >= '0' && _config.FQDN[0] <= '9'))
    {
        DNSClient dns;
        dns.begin(Ethernet.dnsServerIP());
        dns.getHostByName(_config.FQDN, _config.serverIP);
    }
    unsigned long lastAttempt = 0;
    const unsigned long retryInterval = 60 * 1000;
    bool successfullyRegistered = submitConfiguration(&lastAttempt);
    while (!successfullyRegistered)
    {
        if (millis() - lastAttempt > retryInterval)
        {
            successfullyRegistered = submitConfiguration(&lastAttempt);
        }
    }
    return awaitConfirmation();
}

bool HTTPClient::readSSE()
{
    Ethernet.maintain(); //Keep current address assigned by DHCP server.
    if (server.available())
    {
        request, requestMethod, requestError = "";
        request = server.readString((size_t) 4096);
        if (request.length() > 0 && parseRequest())
        {
            Serial.print("New command from: ");
            Serial.println(server.remoteIP());
            Serial.println(request);
            return true;
        }
        Serial.println(requestError);
    }
    else if (!server.connected())
    {
        Serial.println("Lost connection to the Control Server. Trying to re-connect...");
        enlist();
    }
    return false;
}

bool HTTPClient::writeCSE(String method, String data)
{
    if (!server.connected()) return false;
    response, responseReason, responseMessage, responseError = "";
    responseCode = 0;
    Serial.print("Sending Server Client Side Event message...");
    server.println(method + " /sss3/register HTTP/1.1");
    server.println("Connection: keep-alive");
    server.println();
    server.print(data);
    server.flush();
    Serial.println("Done.");
    return true;
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
        Serial.print(_config.mac[3], HEX);
        Serial.print(_config.mac[4], HEX);
        Serial.println(_config.mac[5], HEX);
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

bool HTTPClient::submitConfiguration(unsigned long *lastAttempt)
{
    response, responseReason, responseMessage, responseError = "";
    responseCode = 0;
    Serial.print("Connecting to the Control Server at ");
    Serial.print(_config.serverIP);
    Serial.print("... ");
    if (server.connect(_config.serverIP, 80))
    {
        Serial.println("connected.");
        Serial.print("Generating registration request...");
        String config;
        serializeJson(_config, config);
        Serial.println("Done.");
        Serial.print("Sending configuration message... ");
        server.println("POST /sss3/register HTTP/1.1");
        server.println("Connection: keep-alive");
        server.println();
        server.print(config);
        server.flush();
        Serial.println("complete.");
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

bool HTTPClient::awaitConfirmation()
{
    Ethernet.maintain(); //Keep current address assigned by DHCP server.
    if (server.connected())
    {
        while (!server.available())
        {
            Serial.println("Waiting on server to reply to registration request.");
            delay(500);       
        }
        response = server.readString((size_t) 4096);
        if (parseResponse())
        {
            return ((responseCode >= 200) && (responseCode < 300));
        }
        return false;
    }
    else
    {
        Serial.println("Lost connection to the Server. Trying to re-connect...");
        return enlist();
    }
}

bool HTTPClient::parseResponse()
{
    if (response.length() <= 0) return false;
    std::vector<String> responseArray = tokenizeHTTPMessage(response);
    if (responseArray.size() < 2)
    {
        responseError = "Response is incorrectly formatted";
        return false;
    }
    else if (responseArray[0] != "HTTP/1.1")
    {
        responseError = "Response is missing HTTP/1.1";
        return false;
    }
    responseCode = responseArray[1].toInt();
    if (responseCode == 0) {
        responseError = "Response error code could not be convert to a long";
        return false;
    }
    if (responseArray.size() >= 3) responseReason = responseArray[2];
    if (responseArray.size() >= 4)
    {
        for (int i = 4; i < responseArray.size(); i++)
        {
            responseMessage += " " + responseArray[i];
        }
    }
    return true;
}

bool HTTPClient::parseRequest()
{
    if (request.length() <= 0) return false;
    std::vector<String> requestArray = tokenizeHTTPMessage(request);
    if (requestArray.size() < 3)
    {
        requestError = "Request is incorrectly formatted";
        return false;
    }
    else if (requestArray[2] != "HTTP/1.1")
    {
        requestError = "Request is missing HTTP/1.1";
        return false;
    }
    requestMethod = requestArray[0];
    if (!(requestMethod.equalsIgnoreCase("Delete") || requestMethod.equalsIgnoreCase("Post")))
    {
        requestError = "Request method is not DELETE or POST";
        return false;
    }
    if (requestArray.size() >= 3)
    {
        DeserializationError error = deserializeJson(requestData, requestArray[3]);
        if (error)
        {
            requestError = "Deserializing the request data failed with code ";
            requestError += error.c_str();
            return false;
        }
    }
    return validateJSON();
}

bool HTTPClient::validateJSON()
{
    bool containsIP = requestData.containsKey("IP");
    bool containsCAN_PORT = requestData.containsKey("CAN_PORT");
    bool containsCARLA_PORT = requestData.containsKey("CARLA_PORT");
    if (!containsIP || !containsCAN_PORT || !containsCARLA_PORT)
    {
        requestError = "Request JSON is missing one of the required keys.";
        return false;
    }
    String IP = requestData["IP"];
    if (!IP.startsWith("239.255."))
    {
        requestError = "IP in request JSON does not start with 239.255.";
        return false;
    }
    else if (requestData["CAN_PORT"] < 1025 || requestData["CAN_PORT"] > 65535)
    {
        requestError = "CAN port in request is out of range.";
        return false;
    }
    else if (requestData["CARLA_PORT"] < 1025 || requestData["CARLA_PORT"] > 65535)
    {
        requestError = "CARLA port in request is out of range.";
        return false;
    }
    return true;
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