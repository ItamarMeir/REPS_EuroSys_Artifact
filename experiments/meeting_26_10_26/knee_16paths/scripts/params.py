"""Single source of the fabric numbers of the 16-path study (knee_16paths). Every script imports these instead of retyping 8 / 128 / 64 literals.
Fabric: 2-tier fat tree, k = 32 port switches: 16 hosts per ToR, 16 uplinks per ToR (400G), 16 spines, 32 ToRs, 512 hosts. SRv6: EV -> _paths[ev % P], path j = ToR0 uplink j."""
HOSTS = 512            # hosts (= flows per message: tornado host i -> i + HOSTS/2)
NH = 16                # hosts behind ToR0 = degraded sources, all traced
P = 16                 # SRv6 paths = ToR0 uplinks = `-paths`
PAIR_SHIFT = HOSTS // 2
LATS = (250, 500, 1000, 2000, 4000, 8000, 16000)   # delay of every fabric link, ns
MSGS = 4
CFG_REPS = "h512_p16_msgNh"       # REPS arm   (name + _lat<ns>)
CFG_GOD = "h512_p16_msgNhG"       # god arm (capacity-weighted random draws)
CFG_SOL = "h512_p16_sol"          # one connection, equivalent network (ToR0 uplinks all 0.5)
SEEDS = tuple(range(42, 50))
RTT_BASE_US = 0.33712   # unloaded RTT without link delay: 4 x (4150 B + 64 B ACK) at 400G, printed as network_max_unloaded_rtt 2.33712 at 0.25 us per link
SEND_GAP_US = 4150 * 8 / 200e3   # 0.166 us between sends of the 200G constant-rate sender
def bdp_packets(lat_ns):          # unloaded bandwidth-delay product in packets: RTT = 8 x link delay + RTT_BASE_US
    return (8 * lat_ns / 1000 + RTT_BASE_US) / SEND_GAP_US
def is_bad_ev(ev):                # 5% link = even path
    return ev % P % 2 == 0
