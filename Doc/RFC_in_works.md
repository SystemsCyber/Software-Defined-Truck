https://github.com/inasafe/inasafe/wiki/How-to-write-an-RFC

# RFC: Considerations for Tunneling Automotive Sensor Signals Over UDP

## Problem Statement
* Exposing CAN-based controllers can increase scalability of experimentation
* In-vehicle CAN-based controllers can communicate over faster, possibly reliable overlays, while ensuring backward compatibility
* Sensor signals can also communicated directly to the corresponding ECU pins
* This RFC describes some of the considerations for designing such an overlay

## Duration

## Current state
Draft

## Proposers
* Jeremy Daily
* Subhojeet Mukherjee
* Jacob Jepson

## Detail

## Solution Requirements
### Quality
* Reliability
* Low latency
* Fault tolerance
  
### Functional
* Integration of user knowledge in quality enhancement

## Proposal

### System Blocks

### Block Interactions
```mermaid
sequenceDiagram
    par
        ECU-->>SSSF: CAN Frame
        SSSF ->> SSSF: CAN_Frame_forward_processing()
        SSSF-->>Other Nodes: WrappedCANBuffer
        Other Nodes ->> Other Nodes: CAN_Frame_reverse_processing()
        Other Nodes ->> Other Nodes: Update_health_report()
        Note over Other Nodes: Other nodes include other SSFs and the SimClient
    and
        loop every 1 sec
        Other Nodes ->> Other Nodes: Periodic_health_check()
        end
    and
        loop every inter_frame_space
        Other Nodes ->> their ECUs: CAN frame
        Note over Other Nodes, their ECUs: what should be the interframe space? 
        Note over Other Nodes, their ECUs: Would'nt this delay the whole asynchronous sequence?
        end
    end
```
<center> CAN Frame Exchange </center>
* Periodic health check is required to ensure that even if the SSSF does not recieve a frame from some other node, the health reports are still updated every 1 sec

```mermaid
sequenceDiagram
    CARLA -->> SimClient: Sensor readings 
    Note over CARLA, SimClient: Readings like throttle, brake, wheel speed etc.
    SimClient ->> SimClient: store **last_sensor_sequence**
    SimClient -->> SSSF: SensorFrame
    SSSF ->> SSSF: Convert sensor signal to PWN etc.
    SSSF -->> ECU: Signals to ECU Pins
    ECU-->>SSSF: CAN Frame
    SSSF ->> SSSF: ** CAN Frame Forwarding **
    SSSF -->> SimClient: WrappedCANBuffer
    alt WrappedCANBuffer != last_sensor_sequence and frame_seq_timer expired and num_retransmited < max_retransmits
        SimClient -->> SSSF: RequestFor_SensorFrame{recv_id}       
        Note over SimClient: num_retransmited ++
        SimClient ->> SimClient: reset frame_seq_timer
    end
```
<center> Sensor Signal Forwarding </center>

* Here *frame_seq_timer* is calculated as $\frac{1}{max\_retransmits * frame rate}$ and *max_retransmits* and *frame_rate* are provided by the user


```mermaid
classDiagram
    direction LR
    class WrappedCANFrame{
        id
        dlc
        data
        iface
    }
    class WrappedCANBuffer{
        sensor_signal_sequence
        numframes 
    }
    WrappedCANBuffer *--"1..n"WrappedCANFrame 
```
* **Future work** derive *num_frames* on-the-fly
  
### Internal Block Architectures
#### SSSF (Smart Sensor Simulator and Forwarder)

#### SimClient

### Block Methods
#### CAN Frame Forward Processing 
```mermaid
flowchart LR
    A[Recieve Frame] --> B[Buffer frame];
    B --> C1{n frames buffered?};
    C1 -->|yes| D[transmit WrappedCANBuffer];
    D --> F[Reset buffer];
    C1 -->|no| E[End];
```
<center> CAN Frame Forward Processing </center>

* *n* above can be user defined or derived from network statistics
* Deriving *n* is kept for future?
* Do we even need this *n*? 
  * We need to experiment to see if the UDP frame rate is lower than CAN frame rate
  * Buffering CAN frames here and unwrapping them and transmitting them periodically at the reciever end can increase latency significantly
  * Alternatively, transmitting all the recieved frames at once may increase the load on ECU and on the SSSF. More importantly, this can cause frame rejection. For example, to prevent Request-overload request frames shall not be responded if they arrive faster than a rate. I think the J1939 standards have such restrictions for other transport PDUs too.
  
#### CAN Frame Reverse Processing 
```mermaid
    flowchart LR
    A[Unwarp the buffer] --> B[Store frames in to_transmit buffer]
```
<center> CAN Frame Reverse Processing </center>

#### Health Inspection
```mermaid
sequenceDiagram
    Note over ECU: ECU denotes all instances in the network
    ClientECU->>ECU: RequestFor_HealthReport
    ECU->>ECU: HeatlhEvaluator::get_health_report() 
    ECU-->>ClientECU: HealthReport

```
<center>Health Inspection Process</center>

```mermaid
classDiagram
    class HealthCore{
        min
        max
        avg
    }
    class NodeReport{
        Latency: HealthCore
        DropCount: HealthCore
        DataRate: HealthCore
    }
    class HealthReport
    HealthReport *--"1..n" NodeReport
```
<center>Health Inspection Data Structures</center>

## Record of Votes

## Resolution

## CC
