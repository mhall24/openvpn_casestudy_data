#!/bin/env python

import os
import sys
import subprocess
import re
import time

delta = 1.0

def get_router_cpu():
    P = subprocess.Popen(['snmpwalk', '-v', '1', '-c', 'public', '192.168.2.1', 'hrSWRunPerfCPU'], stdout=subprocess.PIPE)
    P.wait()
    s = P.stdout.read()
    R = re.findall('HOST-RESOURCES-MIB::hrSWRunPerfCPU\.\d+ = INTEGER: (\d+)', s)
    R = [int(x) for x in R]
    return sum(R)

while True:
    cpu0 = get_router_cpu()
    time.sleep(delta)
    cpu1 = get_router_cpu()

    print 'cpu0:  %d' % cpu0
    print 'cpu1:  %d' % cpu1
    print ''
    print 'cpu1-cpu0:  %d' % (cpu1-cpu0)
    print 'cpu util:   %f' % (100 * (cpu1-cpu0)/delta / 100.0)
