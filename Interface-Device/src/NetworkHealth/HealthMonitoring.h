// #include <Arduino.h>

// #TODO move this #define to some config header
// #define NUM_CONSTRUCTS 2 //For now it is sequence and timestamp

// class HealthEvaluator
// {
//     private:
//         struct health_core // CARLA frame information struct
//         {
//             uint32_t min;
//             uint32_t max;
//             uint32_t avg;
//         };
//         struct health_core drop_count = {4294967295, 0, 0};
//         struct health_core latency = {4294967295, 0, 0 };
//         uint8_t prev_constructs[NUM_CONSTRUCTS] = {0,0};
//         uint8_t num_packets_in_this_window = 0;
//         void update_health_core(struct health_core *core_to_update, uint32_t latest_construct, uint32_t prev_construct);

//     public:
//         HealthEvaluator() = default;
//         void update_health_report(uint8_t recv_node_id, uint32_t seq,  uint32_t num_can_frames_transported, uint32_t timestamp);
//         void get_health_report();
// };