#include "statefulecnqueue.h"
#include "uecpacket.h"
#include "compositequeue.h"

uint32_t StatefulECNQueue::_max_incumbents_param = 6;
simtime_picosec StatefulECNQueue::_idle_timeout_ps_param = timeFromUs(30u); // ~5x RTT for k=6 fat-tree

StatefulECNQueue::StatefulECNQueue(linkspeed_bps bitrate, mem_b maxsize,
                                   EventList& eventlist, QueueLogger* logger)
    : Queue(bitrate, maxsize, eventlist, logger),
      _max_incumbents(_max_incumbents_param),
      _idle_timeout_ps(_idle_timeout_ps_param),
      _ecn_threshold(0),
      _enabled(true) {}

void StatefulECNQueue::evict_expired() {
    simtime_picosec now = eventlist().now();
    for (auto it = _incumbents.begin(); it != _incumbents.end(); ) {
        if (now - it->second.last_seen > _idle_timeout_ps)
            it = _incumbents.erase(it);
        else
            ++it;
    }
}

void StatefulECNQueue::receivePacket(Packet& pkt) {
    bool admitted = false;  // sub-flow holds (or was just granted) a slot
    if (_enabled && pkt.type() == UECDATA) {
        SubflowKey key{pkt.flow_id(), pkt.pathid()};
        auto it = _incumbents.find(key);
        simtime_picosec now = eventlist().now();

        if (it != _incumbents.end()) {
            // Incumbent: grant access, clear ECN
            it->second.last_seen = now;
            pkt.set_flags(pkt.flags() & ~ECN_CE);
            admitted = true;
        } else {
            // New sub-flow: lazily evict expired entries, then check capacity
            evict_expired();
            if (_incumbents.size() < _max_incumbents) {
                _incumbents[key] = {now};
                pkt.set_flags(pkt.flags() & ~ECN_CE);
                admitted = true;
            } else {
                // Link full: reject newcomer with ECN = 1
                pkt.set_flags(pkt.flags() | ECN_CE);
            }
        }
    }
    // Absolute incumbent advantage: admitted sub-flows are never re-marked
    // by queue-depth ECN. Only rejected newcomers and non-tracked packets
    // (e.g. when _enabled=false outside the Leaf Exception) can be marked here.
    if (!admitted && _ecn_threshold > 0
        && _queuesize + (mem_b)pkt.size() > _ecn_threshold) {
        pkt.set_flags(pkt.flags() | ECN_CE);
    }
    if (CompositeQueue::_log_ecn_timeseries && _switch && pkt.type() == UECDATA) {
        bool marked = (pkt.flags() & ECN_CE) != 0;
        CompositeQueue::record_ecn_bin(eventlist().now(), _switch->getType(), marked);
    }
    Queue::receivePacket(pkt);
}
