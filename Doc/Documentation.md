Software-defined X-in-the-loop Testbench for Controller Area Network Experiments
==============

# Features
* Long distance CAN overlays
  * Reconfigurable
* Real ECUs
* Optional reliability
* X-in-the-loop integration
  * Fidelity
* Heath monitoring for both X-ih-the-loop and CAN overlays

# Components and data structures

```plantuml
@startuml
title <u> System Components</u>
class "Smart Sensor Simulator and Forwarder" as SSSF
class Controller
class HTTPClient
class CANNode{
    OverlayIP: some local multicast IP
}
class SensorNode{
    OverlayIP: some local multicast IP
}
CANNode <|-d- SensorNode
CANNode <|-d- HTTPClient
HTTPClient <|-d- Controller
HTTPClient <|-d- SSSF
SensorNode <|-d- Controller
SensorNode <|-d- SSSF
CANNode -- CANNode: multicast UDP overlay
@enduml
```
* SSSF Smart Sensor Simulator and Forwarder

```plantuml
@startuml
    title <u>Communication Data Structures</u>

    abstract class COMMBLOCK{
        uint32_t id
        uint32_t frame_number
        uint32_t timestamp
        {abstract} # uint8_t type
    }

    class WSenseBlock{
        type = 2
        uint8_t num_signals
        float signals[19]
    }
    COMMBLOCK <|- WSenseBlock

    class WCANFrame{
        uint32_t id
        uint8_t dlc
        uint64_t data
        char[4] iface
    }
    WCANFrame .|> FlexCAN.CAN_message_t
    WCANFrame .|> FlexCAN.CANFD_message_t
    note right of WCANFrame: for data, we can try uint64_t but \nonly if the compiler permits, \nelse we should move to uint32_t[2]
    class WCANBlock{
        type = 1
        uin32_t sequence_number
        uint8_t buffer_size
        bool need_response
    }

    COMMBLOCK <|- WCANBlock
    WCANBlock *--"1..buffer size"WCANFrame 
@enduml
```

```plantuml
@startuml
    title <u>Health Monitoring Data Structures</u>
    class HealthBasics {
        uint32_t lastMessageTime
        uint32_t lastSequenceNumber
    }
    note right of HealthBasics: The difference between HealthBasics and HealthCore,\nis that HealthBasics contains "per-node"\ninformation, where as HealthCore contains\n"per-node-per-statistic" information.
    class HealthCore{
        -uint32_t count
        +float min
        +float max
        +float avg
        +float variance
        -float sumOfSquaredDifferences
    }
    note right of HealthCore: How would we actually implement count and\nsumOfSquaredDifferences in a private way?

    class NodeReport{
        latency: HealthCore
        jitter: HealthCore
        packetLoss: float
        goodput: HealthCore
    }
    class HealthReport
    HealthReport *--"1..n" NodeReport
@enduml
```

# Behavior Models


```plantuml
@startuml
title <u>CAN Communication (CANCOMM)</u>

|Sending CANNode|
start
partition send{
    :w = New WCANBlock (
        frame_number = **global** frame_number
        )
    w.need_response = **global** buffer_has_critical_frame|
    : Transmit WCANBlock;
    :**global** buffer_has_critical_frame = False|
}
|Recieving CANNodes|
: Recieve WCANBlock = w, say;
partition recv{
    : send CAN messages to the ECU;
    note right
    We need to understand how we send the unpacked frames here?
    In talks with Dr.Daily
    ** FOR NOW ASSUME BUFFER SIZE = 1 **
    end note
    if (w.need_response) then (yes)
    : send an acknoledgement frame; 
    note right 
    Should be a separate ack or piggybacked on the transmitted frames?
    * In the second case, every CAN frame will grow in size by
    num_nodes_in_network * 32 bits. This means slow processing.
    * In the first case, network usage may be doubled and for UDP that means
    packets dropped
    end note
    endif
    partition heatlh_update{
        : Set healthreport[sender_id] = \nmin(healthreport[sender_id].feature.min, \ncalculated feature)|
        : Set healthreport[sender_id] = \nmax(healthreport[sender_id].feature.max, \ncalculated feature)|
        : Set healthreport[sender_id].(mean, variance) = \nwelford(healthreport[sender_id].\nfeature.some_other_quick_statistic, calculated feature)|
    }
    note right 
    calculated features can be \n
    **global** current_ntp_synced_time - w.timestamp
    w.seq - **global** last_seq - w.buffer_size
    (w.ts - last_recieved_ts)/w.buffer_size
    end note
}
stop
@enduml
```

```plantuml
@startuml
title <u>CAN Receipt (CANRECPT)</u>

|ECU|
start
: Transmit CAN frame;
|Connected CANNodes|
: Recieve CAN frame;
partition recv{
    if (frame matches list of critical frames) then (yes)
        : **global** buffer_has_critical_frame = True;
        note right 
        WIZNET chip will not support more than 4 sockets, 
        so we cannot initiate separate TCP + UDP connections.
        This is aside of the heavy load for TCP handshake already. 
        Also, so many TCP connection will make the uni-core processor slow.
        end note
    endif
    if (**global** signals's length > 0) then (yes)
        while (signal in frame's data) then (yes)
            : convert_signal_to_l2();
            floating note right: for us, this will be a j1939 convert
            : replace in frame;
        endwhile
        floating note right: we may have to replace the while loop with a hashmap
    endif
    : Buffer frame;
    note right
        Do we need to buffer?
        ** FOR NOW ASSUME BUFFER SIZE = 1 **
    end note
    if (len(buffer) == buffer size) then (yes)
    : call CANCOMM.send(); 
    endif
}
stop
@enduml
```

```plantuml
@startuml
title Sensor Signal Exchange (SIGCOMM)

|Sending CANNode|
start
while (signal[i] is not NULL)
    if (**define** forward to ECU pins) then (yes)
    partition sensor_pin_simulation{
        : send signal[i] to ECU if SSS2 features are available;
    }
    else if (**define** forward to ECU CAN port) then (yes)
    partition can_control_simulation{
        : convert to control message like TSC1;
        : forward to ECU;
    }
    else
    partition default_data_overwrite{
        : set **global** signals = recievd wsenseblock.signals;
    }
endif

endwhile
stop
@enduml
```

```plantuml
@startuml
title Main Loop Routing

|Recieving CANNode|
start
if (recvieved CAN frame) then (yes)
    : call CANRECPT.recv();
else
    : cast udp data to a COMMBLOCK = w say;
    if (w.type == 1) then
    : call SIGCOMM.handle();
    else if (w.type == 2 and recieved iface is UDP)
    : call CANCOMM.recv();
endif
endif

stop
@enduml
```


# Future work
* Security