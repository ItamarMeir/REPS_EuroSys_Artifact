#!/usr/bin/env python3
"""timed.py <stdout_file> <cmd...> : run cmd, stdout+stderr to file, print 'wall_s peak_rss_MB rc' to stderr."""
import resource, subprocess, sys, time
t = time.time()
with open(sys.argv[1], "w") as f:
    rc = subprocess.call(sys.argv[2:], stdout=f, stderr=subprocess.STDOUT)
r = resource.getrusage(resource.RUSAGE_CHILDREN)
print("%.1fs %dMB rc=%d" % (time.time() - t, r.ru_maxrss // 1024, rc), file=sys.stderr)
