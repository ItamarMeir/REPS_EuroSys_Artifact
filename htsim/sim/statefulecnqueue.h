#ifndef STATEFULECNQUEUE_H
#define STATEFULECNQUEUE_H

#include <unordered_map>
#include "queue.h"
#include "ecn.h"

struct SubflowKey {
    uint32_t flow_id;
    uint32_t ev;
    bool operator==(const SubflowKey& o) const {
        return flow_id == o.flow_id && ev == o.ev;
    }
};

struct SubflowKeyHash {
    size_t operator()(const SubflowKey& k) const {
        return std::hash<uint64_t>()((uint64_t)k.flow_id << 32 | k.ev);
    }
};

// StatefulECNQueue implements "Incumbent Advantage":
// - The first sub-flow (flow_id, ev) to arrive on a link claims a slot.
// - Incumbents have ECN explicitly cleared (granted access).
// - New sub-flows when the link is full get ECN = 1 (rejected).
// - Idle incumbents are lazily evicted after _idle_timeout_ps picoseconds.
// - Disabled on ToR downlinks (Leaf Exception) via set_enabled(false).
class StatefulECNQueue : public Queue {
public:
    StatefulECNQueue(linkspeed_bps bitrate, mem_b maxsize,
                     EventList& eventlist, QueueLogger* logger);

    void receivePacket(Packet& pkt) override;

    void set_enabled(bool e)               { _enabled = e; }
    void set_max_incumbents(uint32_t m)    { _max_incumbents = m; }
    void set_idle_timeout_ps(simtime_picosec t) { _idle_timeout_ps = t; }
    void set_ecn_threshold(mem_b thresh)   { _ecn_threshold = thresh; }

    static uint32_t _max_incumbents_param;
    static simtime_picosec _idle_timeout_ps_param;

private:
    struct Entry { simtime_picosec last_seen; };
    std::unordered_map<SubflowKey, Entry, SubflowKeyHash> _incumbents;

    uint32_t _max_incumbents;
    simtime_picosec _idle_timeout_ps;
    mem_b _ecn_threshold;  // 0 = disabled; congestion ECN applied in addition to incumbent logic
    bool _enabled;

    void evict_expired();
};

#endif
