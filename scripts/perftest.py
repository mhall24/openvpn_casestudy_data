#!/bin/env python

import os
import sys
import time
import subprocess
import signal
import re
import fcntl
import math
import types
from os import path

''' Todo:
    -----
    1) Script the automatic creation of the openvpn configuration files for both client and server.
    2) Script the key generation process.  This will be useful for future tests using different size keys.
    3) Add options to the command-line.
'''

''' Useful command for looking at the CPU cycles on the router:
    -----------------------------------------------------------
        watch snmpwalk -v 1 -c public 192.168.2.1 hrSWRunPerfCPU
'''


ETH = "eth0"
TAP = "tap0"
TUN = "tun0"

DEFAULT_NIC_INT = ETH
DEFAULT_TUN_INT = TAP

WorkloadDict  = {"Video": "workloads/workload1",
                 "Text" : "workloads/workload2"}
InterfaceDict = {"tun":"tun0",
                 "tap":"tap1",
                 "tapbr":"tap0"}

def fracfact(s):
    import numpy

    # Get the unique list of sorted factors
    factors = set(s) & set('abcdefghijklmnopqrstuvwxyz')
    factors = sorted(factors)
    k = len(factors)

    # Create a dictionary of the pattern for each factor
    d = {"I":numpy.ones(2**k, dtype=numpy.int32)}
    for (i,f) in enumerate(factors):
        d[f] = numpy.array([{False:-1, True:1}[x] for x in (numpy.arange(2**k) & 2**(k-i-1) != 0)])

    # Split the string into each factor's terms
    terms = s.split()

    L = []
    for t in terms:
        v = numpy.copy(d["I"])
        for f in set(t):
            v *= d[f]
        L.append(v)

    M = numpy.matrix(L).transpose()

    return M


def MakeNonblocking(F):
    fd = F.fileno()
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)


class Tee:
    files = None
    def __init__(self, files=None):
        if files is None: files = (sys.stdout,)
        self.files = files
    def write(self, string):
        for file in self.files:
            if not file.closed:
                file.write(string)
    def flush(self):
        for file in self.files:
            if not file.closed:
                file.flush()
    def __getattr__(self, name):
        return getattr(self.files[0], name)
    def __setattr__(self, name, value):
        if name in dir(self): self.__dict__[name] = value
        else: setattr(self.files[0], name, value)


class OpenVPN_Server:
    def __init__(self, RouterIP, Delay=0.5):
        self.P = None
        self.RouterIP = RouterIP
        self.Delay = Delay
    def __del__(self):
        if self.P != None:
            try:
                self.send_ctrl_c()
                self.kill_openvpn()
                self.disconnect()
                print 'Killed OpenVPN server'
            except:
                print 'Unsuccessful killing OpenVPN server'
    def connect(self):
        self.P = subprocess.Popen(['telnet', self.RouterIP], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        MakeNonblocking(self.P.stdout)

        # Send the username and password
        time.sleep(self.Delay)
        self.P.stdin.write('root\n')
        time.sleep(self.Delay)
        self.P.stdin.write('mypassword\n')
        time.sleep(self.Delay)
    def disconnect(self):
        self.send_ctrl_c()
        self.P.stdin.write('exit\n')
        time.sleep(self.Delay)
        self.P.stdin.close()
        try:
            try:
                os.kill(self.P.pid, signal.SIGTERM)
            finally:
                self.P = None
        except OSError:
            pass
    def send_ctrl_c(self):
        self.P.stdin.write('\x03')
        time.sleep(self.Delay)
    def start_openvpn(self, config_filename):
        self.P.stdin.write('openvpn /mmc/etc/openvpn/%s\n' % config_filename)
        time.sleep(self.Delay)
        print 'Started OpenVPN server'
    def get_openvpn_pid(self):
        self.P.stdout.flush()
        self.P.stdin.write('ps\n')
        time.sleep(self.Delay)
        R = re.findall("(\d+) +root +.* +openvpn", os.read(self.P.stdout.fileno(), 100000))[-1:]
        if len(R) > 0:
            return int(R[0])
        else:
            return None
    def kill_pid(self, pid):
        self.P.stdin.write('kill %d\n' % pid)
        time.sleep(self.Delay)
    def kill_openvpn(self):
        pid = self.get_openvpn_pid()
        if pid != None:
            self.kill_pid(pid)
            return True
        return False


class OpenVPN_Client:
    def __init__(self):
        self.P = None
    def __del__(self):
        if self.P != None:
            try:
                self.stop_openvpn()
                print 'Killed OpenVPN client'
            except:
                print 'Unsuccessful killing OpenVPN client'
    def start_openvpn(self, config_filename):
        cwd = path.realpath(os.curdir)
        os.chdir('/etc/openvpn/testrouter')
        try:
            self.P = subprocess.Popen(['openvpn', path.join(config_filename)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print 'Started OpenVPN client'
        finally:
            os.chdir(cwd)
        MakeNonblocking(self.P.stdout)
    def stop_openvpn(self):
        try:
            try:
                os.kill(self.P.pid, signal.SIGTERM)
            finally:
                self.P = None
        except OSError:
            pass
    def kill_openvpn(self):
        p1 = subprocess.Popen(['pkill', 'openvpn'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p1.wait()


def ConfigBuilder(HostType, Interface, Protocol, Compression, Encryption):
    return '%s-%s-%s-%s-%s.conf' % (HostType, Interface, Protocol, Compression, Encryption)


def JoinDicts(*args):
    d = {}
    for a in args:
        for i in a.items():
            d[i[0]] = i[1]
    return d


def KillProcess(pid, sig=signal.SIGTERM):
    try:
        os.kill(pid, sig)
    except:
        pass


def ReadOutput(Type, Data, **kwds):
    if Type == "iperf_tcp":
        s = re.findall("(\d+\.?\d*) ([KM])bits/sec", Data)
        if kwds.get('Tradeoff'):
            s = s[0:len(s)/2-1] + s[len(s)/2:-1]
        else:
            s = s[:-1]
        d = [float(x[0])*{"K":1e3, "M":1e6}[x[1]] for x in s]
        return d
    elif Type == "iperf_udp":
        s = re.findall("\[.*\] .* sec .* [KM]Bytes .* [KM]bits/sec +(\d+\.\d+) ms *(\d+)/ *(\d+) \((\d+(?:\.\d+)?)\%\)", Data)
        L = []
        for x in s:
            jitter = float(x[0])*1e-3
            packets_lost  = int(x[1])
            packets_total = int(x[2])
            percent_loss  = float(packets_lost) / float(packets_total)

            d = {"jitter":        jitter,
                 "packets_lost":  packets_lost,
                 "packets_total": packets_total,
                 "percent_loss":  percent_loss}
            L.append(d)
        return L
    elif Type == "ping":
        s = re.findall("(\d+) packets transmitted, (\d+) received, (\d+)% packet loss, time (\d+)ms", Data) + \
            re.findall("rtt min/avg/max/mdev = (\d+\.\d+)/(\d+\.\d+)/(\d+\.\d+)/(\d+\.\d+) ms", Data)

        packets_tx = int(s[0][0])-1
        packets_rx = int(s[0][1])
        if packets_tx < packets_rx: packets_tx += 1
        percent_loss = 1.0 - float(packets_rx)/float(packets_tx)
        time_elapsed = float(s[0][3])*1e-3
        rtt_min = float(s[1][0])*1e-3
        rtt_avg = float(s[1][1])*1e-3
        rtt_max = float(s[1][2])*1e-3
        rtt_mdev = float(s[1][3])*1e-3

        d = {"packets_tx":   packets_tx,
             "packets_rx":   packets_rx,
             "percent_loss": percent_loss,
             "time_elapsed": time_elapsed,
             "rtt_min":      rtt_min,
             "rtt_avg":      rtt_avg,
             "rtt_max":      rtt_max,
             "rtt_mdev":     rtt_mdev}
        return d
    elif Type == "sar":
        NicInt = kwds.get('NicInt', DEFAULT_NIC_INT)
        TunInt = kwds.get('TunInt', DEFAULT_TUN_INT)

        s = Data.splitlines()
        s = [x for x in s if re.search('(%s)|(%s)|(IFACE)|(all)' % (NicInt, TunInt), x) != None]
        s = [x for x in s if re.search('Average',x) == None]
        s = [x.split() for x in s]

        iface = {}
        for i in range(len(s)):
            iface.setdefault(s[i][2], [])
            iface[s[i][2]].append(s[i][3:])
        d = []
        for i in range(len(iface[ETH])):
            nic_rx_packets = float(iface[NicInt][i][0])
            nic_tx_packets = float(iface[NicInt][i][1])
            nic_rx_bytes   = float(iface[NicInt][i][2])
            nic_tx_bytes   = float(iface[NicInt][i][3])
            tun_rx_packets = float(iface[TunInt][i][0])
            tun_tx_packets = float(iface[TunInt][i][1])
            tun_rx_bytes   = float(iface[TunInt][i][2])
            tun_tx_bytes   = float(iface[TunInt][i][3])
            cpu_util       = (100 - float(iface['all'][i][5])) / 100.0
            link_util_tx   = nic_tx_bytes / 100e6
            link_util_rx   = nic_rx_bytes / 100e6

            try:
                overhead_tx   = (nic_tx_bytes - tun_tx_bytes) / nic_tx_packets
            except ZeroDivisionError:
                overhead_tx   = None
            try:
                overhead_rx   = (nic_rx_bytes - tun_rx_bytes) / nic_rx_packets
            except ZeroDivisionError:
                overhead_rx   = None

            d.append({"nic_rxpck/s":  nic_rx_packets,
                      "nic_txpck/s":  nic_tx_packets,
                      "nic_rxbyt/s":  nic_rx_bytes,
                      "nic_txbyt/s":  nic_tx_bytes,
                      "tun_rxpck/s":  tun_rx_packets,
                      "tun_txpck/s":  tun_tx_packets,
                      "tun_rxbyt/s":  tun_rx_bytes,
                      "tun_txbyt/s":  tun_tx_bytes,
                      "cpu_util":     cpu_util,
                      "link_util_tx": link_util_tx,
                      "link_util_rx": link_util_rx,
                      "overhead_tx":  overhead_tx,
                      "overhead_rx":  overhead_rx})
        return d
    else:
        return None


def ShowData(Type, Data):
    if Type == "sar":
        print '    eth        tap        diff      overhead    %link    %cpu'
        for d in Data:
            print '%11.1f %11.1f %11.1f %11.1f  %6.2f%%  %6.2f%%' % (d["nic_txbyt/s"], d["tun_txbyt/s"], d["nic_txbyt/s"]-d["tun_txbyt/s"],
                d["overhead"], d["link_util"], d["cpu_util"])
    elif Type == "merged":
        print '  bandwidth      '+ETH+'        '+TAP+'         diff      overhead   %link    %cpu   efficiency'
        for d in Data:
            #print '%6.2f Mbit/s %11.1f %11.1f %11.1f %11.1f  %6.2f%%  %6.2f%%' % (d["tcp_bandwidth"]/1e6, d["nic_txbyt/s"], d["tun_txbyt/s"], d["nic_txbyt/s"]-d["tun_txbyt/s"],
                #d["overhead"], d["link_util"], d["cpu_util"])
            print '%6.2f Mbps %6.2f Mbps %6.2f Mbps %11.1f  %11.1f  %6.2f%%  %6.2f%%  %6.1f%%' % (d["tcp_bandwidth"]/1e6, d["nic_txbyt/s"]*8/1e6,
                d["tun_txbyt/s"]*8/1e6, d["nic_txbyt/s"]-d["tun_txbyt/s"], d["overhead"], d["link_util"]*100, d["cpu_util"]*100, d["efficiency"]*100)


def RunTCPTest(Endpoint, Interval, Count, Tradeoff=False, Workload=None, PayloadLength=None, MSS=None, NicInt=DEFAULT_NIC_INT, TunInt=DEFAULT_TUN_INT):
    # Create the command line arguments for iperf
    iperf_args = ['iperf']
    iperf_args += ['-c', Endpoint]
    iperf_args += ['-i', str(Interval)]
    iperf_args += ['-t', str(Count*Interval)]
    if Tradeoff: iperf_args += ['-r']
    if PayloadLength != None: iperf_args += ['-N', '-l', str(PayloadLength)]
    if Workload != None: iperf_args += ['-F', Workload]
    if MSS != None: iperf_args += ['-N', '-M', str(MSS)]

    # Create the command line arguments for sar
    sar_args = ['sar']
    sar_args += ['-n', 'DEV']
    sar_args += ['-p']
    sar_args += ['-u']
    sar_args += [str(Interval), str(Count * (2 if Tradeoff else 1))]

    run_test = True
    while run_test:
        # Run iperf (tcp performance test) and sar (collect & report system information)
        p1 = subprocess.Popen(iperf_args, stdout=subprocess.PIPE)
        p2 = subprocess.Popen(sar_args,   stdout=subprocess.PIPE)

        # Wait for both processes to finish
        try:
            p1.wait()
            p2.wait()
        finally:
            KillProcess(p1.pid)
            KillProcess(p2.pid)

        # Read the outputs
        out1 = p1.stdout.read()
        out2 = p2.stdout.read()

        # Read iperf and sar data
        iperf_data = ReadOutput("iperf_tcp", out1, Tradeoff=Tradeoff)
        sar_data   = ReadOutput("sar", out2, NicInt=NicInt, TunInt=TunInt)

        effective_count = Count * (2 if Tradeoff else 1)
        if len(iperf_data) != effective_count:
            print 'Only %d data results were returned from iperf but expected %d.' % (len(iperf_data), effective_count)
            print ''
            print 'Iperf Output'
            print '------------'
            print out1
            print ''
            print 'Sar Output'
            print '----------'
            print out2
            print ''
            print 'Redoing test...'
            print ''
        elif len(sar_data) != effective_count:
            print 'Only %d data results were returned from sar but expected %d.' % (len(sar_data), effective_count)
            print ''
            print 'Iperf Output'
            print '------------'
            print out1
            print ''
            print 'Sar Output'
            print '----------'
            print out2
            print ''
            print 'Redoing test...'
            print ''
        else:
            run_test = False

    # Merge results from iperf and sar
    results = []
    for i in range(len(iperf_data)):
        e = {"tcp_bandwidth":iperf_data[i]}
        for kv in sar_data[i].items():
            e[kv[0]] = kv[1]
        try:
            e["efficiency_tx"] = e["tcp_bandwidth"] / (e["nic_txbyt/s"]*8)
        except ZeroDivisionError:
            e["efficiency_tx"] = None
        try:
            e["efficiency_rx"] = e["tcp_bandwidth"] / (e["nic_rxbyt/s"]*8)
        except ZeroDivisionError:
            e["efficiency_rx"] = None
        results.append(e)

    # Split results if tradeoff
    if Tradeoff:
        results = (results[0:len(results)/2], results[len(results)/2:])

    # Return the results
    return ("TCP Test", results, {"Tradeoff":Tradeoff})


def RunUDPTest(Endpoint, Interval, Count, Tradeoff=False, Workload=None, PayloadLength=None, MSS=None, NicInt=DEFAULT_NIC_INT, TunInt=DEFAULT_TUN_INT):
    # Create the command line arguments for iperf
    iperf_args = ['iperf']
    iperf_args += ['-c', Endpoint]
    iperf_args += ['-u']
    iperf_args += ['-t', str(Interval)]

    if Tradeoff: iperf_args += ['-r']
    if PayloadLength != None: iperf_args += ['-l', str(PayloadLength)]
    if Workload != None: iperf_args += ['-F', Workload]
    if MSS != None: iperf_args += ['-M', str(MSS)]

    # Create the command line arguments for sar
    sar_args = ['sar']
    sar_args += ['-n', 'DEV']
    sar_args += ['-p']
    sar_args += ['-u']
    sar_args += [str(Interval), str(2 if Tradeoff else 1)]

    # Run iperf and sar
    p1 = [None]*Count
    p2 = [None]*Count

    for i in range(Count):
        p1[i] = subprocess.Popen(iperf_args, stdout=subprocess.PIPE)
        p2[i] = subprocess.Popen(sar_args,   stdout=subprocess.PIPE)
        try:
            try:
                p1[i].wait()
                p2[i].wait()
            finally:
                KillProcess(p1[i].pid)
                KillProcess(p2[i].pid)
        except:
            try:
                print 'Iperf Output'
                print '------------'
                print p1[i].stdout.read()
                print ''
            except:
                pass
            raise
        time.sleep(1.000)

    # Read the output
    out1       = [None]*Count
    out2       = [None]*Count
    iperf_data = [None]*Count
    sar_data   = [None]*Count
    for i in range(len(p1)):
        out1[i] = p1[i].stdout.read()
        out2[i] = p2[i].stdout.read()
        iperf_data[i] = ReadOutput("iperf_udp", out1[i])
        sar_data[i]   = ReadOutput("sar",       out2[i], NicInt=NicInt, TunInt=TunInt)

    # Merge data
    results = []
    for j in range(len(iperf_data[0])):
        R = []
        for i in range(len(iperf_data)):
            R.append(JoinDicts(iperf_data[i][j], sar_data[i][j]))
        results.append(R)

    if Tradeoff:
        results = (results[0], results[1])
    else:
        results = results[0]

    return ("UDP Test", results, {"Tradeoff":Tradeoff})


def RunLatencyTest(Endpoint, Interval, Count, PacketSize=None, NicInt=DEFAULT_NIC_INT, TunInt=DEFAULT_TUN_INT):
    # Create the command line arguments for ping
    ping_args = ['ping']
    ping_args += [Endpoint]
    ping_args += ['-f']
    ping_args += ['-q']

    if PacketSize != None: ping_args += ['-s', str(PacketSize)]

    # Create the command line arguments for sar
    sar_args = ['sar']
    sar_args += ['-n', 'DEV']
    sar_args += ['-p']
    sar_args += ['-u']
    sar_args += [str(Interval), str(Count)]

    # Run ping and sar
    p1 = [None]*Count
    p2 = subprocess.Popen(sar_args,  stdout=subprocess.PIPE)

    for i in range(Count):
        p1[i] = subprocess.Popen(ping_args, stdout=subprocess.PIPE)
        try:
            time.sleep(Interval)
        finally:
            KillProcess(p1[i].pid, signal.SIGINT)       # Send SIGINT (control-C) to process

    # Wait for all processes to finish and read the output
    out1      = [None]*Count
    ping_data = [None]*Count
    for (i,p) in enumerate(p1):
        p.wait()
        out1[i] = p.stdout.read()
        ping_data[i] = ReadOutput("ping", out1[i])
    p2.wait()
    out2 = p2.stdout.read()
    sar_data = ReadOutput("sar", out2, NicInt=NicInt, TunInt=TunInt)

    # Merge data
    results = []
    for i in range(len(ping_data)):
        results.append(JoinDicts(ping_data[i], sar_data[i]))

    return ("Latency Test", results, None)


def ShowResults(Results, Style="P"):
    if Results == None:
        return

    Test = Results[0]
    Data = Results[1]
    Options = Results[2] if Results[2] != None else {}
    d = Options.get("Direction", "tx")
    if Test == "TCP Test":
        if Style in ("B", "P", "C") and not Options.get('Suppress Header'):
            print "TCP test"
            print "------------------"
        if not Options.get('Tradeoff'):
            if Style == "B":
                Options["Suppress Header"] = True
                ShowResults([Test, Data, Options], Style="P")
                ShowResults([Test, Data, Options], Style="C")
            elif Style == "P":
                # Print in human-readable form
                print '  bandwidth      '+ETH+'        '+TAP+'         diff      overhead   %link    %cpu   efficiency'
                for r in Data:
                    print '%6.2f Mbps %6.2f Mbps %6.2f Mbps %11.1f  %11.1f  %6.2f%%  %6.2f%%  %6.1f%%' % (r["tcp_bandwidth"]/1e6, r["nic_"+d+"byt/s"]*8/1e6,
                        r["tun_"+d+"byt/s"]*8/1e6, r["nic_"+d+"byt/s"]-r["tun_"+d+"byt/s"], r["overhead_"+d], r["link_util_"+d]*100, r["cpu_util"]*100, r["efficiency_"+d]*100)
            elif Style == "C":
                # Print in comma-delimited form
                print '\n'.join(ShowResults(Results, Style="R"))
            elif Style == "R":
                # Format in comma-delimited form and return
                R = []
                for r in Data:
                    R.append('%d,%d,%d,%f,%f,%f,%f' % (r["tcp_bandwidth"], r["nic_"+d+"byt/s"]*8, r["tun_"+d+"byt/s"]*8, r["nic_"+d+"pck/s"],
                        r["tun_"+d+"pck/s"], r["link_util"], r["cpu_util"]))
                return R
        else:
            if Style == "B":
                Options["Suppress Header"] = True
                ShowResults([Test, Data, Options], Style="P")
                ShowResults([Test, Data, Options], Style="C")
            elif Style == "P":
                # Print in human-readable form
                print "Client-to-Server"
                ShowResults((Test, Data[0], {"Direction":"tx", "Suppress Header":True}), Style="P")
                print "Server-to-Client"
                ShowResults((Test, Data[1], {"Direction":"rx", "Suppress Header":True}), Style="P")
            elif Style == "C":
                # Print in comma-delimited form
                print '\n'.join(ShowResults(Results, Style="R"))
            elif Style == "R":
                # Format in comma-delimited form and return
                R = []
                for i in range(len(Data[0])):
                    c2s = Data[0][i]
                    s2c = Data[1][i]
                    R.append((',%d,%d,%d,%f,%f,%f,%f,' % (c2s["tcp_bandwidth"], c2s["nic_txbyt/s"]*8, c2s["tun_txbyt/s"]*8, c2s["nic_txpck/s"],
                                c2s["tun_txpck/s"], c2s["link_util_tx"], c2s["cpu_util"])) +
                             (',%d,%d,%d,%f,%f,%f,%f'  % (s2c["tcp_bandwidth"], s2c["nic_rxbyt/s"]*8, s2c["tun_rxbyt/s"]*8, s2c["nic_rxpck/s"],
                                s2c["tun_rxpck/s"], s2c["link_util_rx"], s2c["cpu_util"])))
                return R
        print ""
    elif Test == "UDP Test":
        if Style in ("B", "P", "C") and not Options.get('Suppress Header'):
            print "UDP test"
            print "------------------"
        if not Options.get('Tradeoff'):
            if Style == "B":
                Options["Suppress Header"] = True
                ShowResults([Test, Data, Options], Style="P")
                ShowResults([Test, Data, Options], Style="C")
            elif Style == "P":
                print "jitter   lost  total   %loss   %cpu"
                for d in Data:
                    print '%6.3f  %5d  %5d  %6.1f  %6.1f' % (d["jitter"]*1e3, d["packets_lost"], d["packets_total"], 100*d["percent_loss"], 100*d["cpu_util"])
            elif Style == "C":
                print '\n'.join(ShowResults(Results, Style="R"))
            elif Style == "R":
                R = []
                for d in Data:
                    R.append('%f,%d,%d,%f,%f' % (d["jitter"], d["packets_lost"], d["packets_total"], d["percent_loss"], d["cpu_util"]))
                return R
        else:
            if Style == "B":
                Options["Suppress Header"] = True
                ShowResults([Test, Data, Options], Style="P")
                ShowResults([Test, Data, Options], Style="C")
            elif Style == "P":
                # Print in human-readable form
                print "Client-to-Server"
                ShowResults((Test, Data[0], {"Direction":"tx", "Suppress Header":True}), Style="P")
                print "Server-to-Client"
                ShowResults((Test, Data[1], {"Direction":"rx", "Suppress Header":True}), Style="P")
            elif Style == "C":
                # Print in comma-delimited form
                for i in range(len(Data[0])):
                    c2s = Data[0][i]
                    s2c = Data[1][i]
                    sys.stdout.write('%f,%d,%d,%f,%f,'  % (c2s["jitter"], c2s["packets_lost"], c2s["packets_total"], c2s["percent_loss"], c2s["cpu_util"]))
                    sys.stdout.write('%f,%d,%d,%f,%f\n' % (s2c["jitter"], s2c["packets_lost"], s2c["packets_total"], s2c["percent_loss"], s2c["cpu_util"]))
            elif Style == "R":
                # Format in comma-delimited form and return
                R = []
                for i in range(len(Data[0])):
                    c2s = Data[0][i]
                    s2c = Data[1][i]
                    R.append(('%f,%d,%d,%f,%f,' % (c2s["jitter"], c2s["packets_lost"], c2s["packets_total"], c2s["percent_loss"], c2s["cpu_util"])) +
                             ('%f,%d,%d,%f,%f'  % (s2c["jitter"], s2c["packets_lost"], s2c["packets_total"], s2c["percent_loss"], s2c["cpu_util"])))
                return R
        print ""
    elif Test == "Latency Test":
        if Style in ("B", "P", "C") and not Options.get('Suppress Header'):
            print "Latency test"
            print "------------------"
        if Style == "B":
            Options["Suppress Header"] = True
            ShowResults([Test, Data, Options], Style="P")
            ShowResults([Test, Data, Options], Style="C")
        elif Style == "P":
            # Print in human-readable form
            print '      packets     loss   rtt min   rtt avg   rtt max   rtt mdev    %cpu'
            for d in Data:
                print ' %5d / %5d  %6.2f%%   %6.3f    %6.3f    %6.3f    %6.3f   %6.2f%%' % (d["packets_rx"], d["packets_tx"], 100*d["percent_loss"],
                    d["rtt_min"]*1e3, d["rtt_avg"]*1e3, d["rtt_max"]*1e3, d["rtt_mdev"]*1e3, 100*d["cpu_util"])
        elif Style == "C":
            # Print in comma-delimited form
            print '\n'.join(ShowResults(Results, Style="R"))
        elif Style == "R":
            # Format in comma-delimited form and return
            R = []
            for d in Data:
                R.append('%d,%d,%f,%f,%f,%f,%f,%f' % (d["packets_rx"], d["packets_tx"], d["percent_loss"],
                    d["rtt_min"], d["rtt_avg"], d["rtt_max"], d["rtt_mdev"], d["cpu_util"]))
            return R
        print ""
    elif Test == "Aggregate":
        if Style in ("B", "P", "C") and not Options.get('Suppress Header'):
            print "Aggregated results"
            print "------------------"
        if Style == "C":
            print '\n'.join(ShowResults(Results, Style="R"))
        elif Style == "R":
            R = []
            for (i,L) in enumerate(Data):
                R.append(ShowResults(L, Style="R"))
            R2 = ['']*len(R[0])
            for i in range(len(R[0])):
                R2[i] = ','.join([x[i] for x in R])
            return R2
        print ""


def RunPerfTest(Endpoint, Interval, Count, Style, Tradeoff_TCPtest=False, Tradeoff_UDPtest=False, Workload=None, PayloadLength=None, NicInt=DEFAULT_NIC_INT, TunInt=DEFAULT_TUN_INT):

    # Do performance test
    results = [None]*3

    t0 = time.time()
    results[0] = RunTCPTest(Endpoint, Interval=Interval, Count=Count, Tradeoff=Tradeoff_TCPtest, Workload=Workload, MSS=PayloadLength, NicInt=NicInt, TunInt=TunInt)
    ShowResults(results[0], Style=Style)
    t1 = time.time()
    results[1] = RunUDPTest(Endpoint, Interval=Interval, Count=Count, Tradeoff=Tradeoff_UDPtest, Workload=Workload, PayloadLength=PayloadLength, NicInt=NicInt, TunInt=TunInt)
    ShowResults(results[1], Style=Style)
    t2 = time.time()
    results[2] = RunLatencyTest(Endpoint, Interval=Interval, Count=Count, NicInt=NicInt, TunInt=TunInt)
    ShowResults(results[2], Style=Style)
    t3 = time.time()

    ShowResults(("Aggregate", results, None), Style="C")

    # Print time results
    print "TCP test time:      %5.1f s" % (t1 - t0)
    print "UDP test time:      %5.1f s" % (t2 - t1)
    print "Latency test time:  %5.1f s" % (t3 - t2)
    print ""
    print "Total elapsed time: %5.1f s" % (t3 - t0)
    print ""


def SetupRunPerfTest(Endpoint, Interval, Count, Style, Interface, Protocol, Compression, Encryption, Workload=None, PayloadLength=None, Tradeoff_TCPtest=False, Tradeoff_UDPtest=False):

    server_conf = ConfigBuilder(HostType='server', Interface=Interface, Protocol=Protocol, Compression=Compression, Encryption=Encryption)
    client_conf = ConfigBuilder(HostType='client', Interface=Interface, Protocol=Protocol, Compression=Compression, Encryption=Encryption)

    connected = False
    while not connected:
        server = OpenVPN_Server('192.168.2.1')
        server.connect()
        server.kill_openvpn()
        server.start_openvpn(server_conf)

        client = OpenVPN_Client()
        client.kill_openvpn()
        client.start_openvpn(client_conf)

        time.sleep(10.0)

        server_output = os.read(server.P.stdout.fileno(), 100000)
        client_output = os.read(client.P.stdout.fileno(), 100000)

        print 'Server Output'
        print '-------------'
        print server_output
        print ''
        print 'Client Output'
        print '-------------'
        print client_output
        print ''

        print 'Ping Output'
        print '-----------'
        P = subprocess.Popen(['ping', '-c', '100', Endpoint], stdout=subprocess.PIPE)
        buf = ''
        ping_count = 0
        while P.poll() == None or len(buf) > 0:
            buf = os.read(P.stdout.fileno(), 1000)
            sys.stdout.write(buf)
            if len(re.findall('\d+ bytes from .*: icmp_seq=\d+ ttl=\d+ time=\d+\.\d+', buf)) > 0:
                ping_count += 1
                if ping_count >= 3:
                    connected = True
                    break
        try:
            os.kill(P.pid, signal.SIGTERM)
        except OSError:
            pass
        print ''

        if connected:
            try:
                client_output += os.read(client.P.stdout.fileno(), 100000)
            except:
                pass
            try:
                TunInt = re.findall("TUN/TAP device (\w+\d+) opened", client_output)[-1]
            except:
                print 'Unable to determine the TUN/TAP device...restarting'
                connected = False
                server = None
                client = None
        else:
            print 'No connection detected...restarting'
            server = None
            client = None

    try:
        # Estimate the expected test time
        estimated_test_time = Interval*Count*(2 if Tradeoff_TCPtest else 1) + (Interval*(2 if Tradeoff_UDPtest else 1)+1)*Count + Interval*Count

        print "Time:            %s"   % time.asctime()
        print ""
        print "Server config:   %s"   % server_conf
        print "Client config:   %s"   % client_conf
        print ""
        print "Endpoint:        %s"   % Endpoint
        print "Interface:       %s"   % Interface
        print "Protocol:        %s"   % Protocol
        print "Compression:     %s"   % Compression
        print "Encryption:      %s"   % Encryption
        print "Interval:        %.1f" % Interval
        print "Count:           %d"   % Count
        print "Workload:        %s"   % Workload
        print "Payload Length:  %s"   % str(PayloadLength)
        print ""
        print "Estimated time:  %.1f s" % estimated_test_time
        print ""

        print "=====>", TunInt
        print ""

        # Do performance test
        RunPerfTest(Endpoint=Endpoint, Interval=Interval, Count=Count, Style=Style, Tradeoff_TCPtest=Tradeoff_TCPtest, Tradeoff_UDPtest=Tradeoff_UDPtest,
            Workload=WorkloadDict[Workload], PayloadLength=PayloadLength, TunInt=TunInt)
    finally:
        server = None
        client = None
        print ""


def GenFF(k, p, pfactors):
    for i in range(2**(k-p)):
        F = []
        x = i
        for j in range(k-p):
            F.append({0:-1,1:1}[x%2])
            x //= 2
        F.reverse()
        for j in range(p):
            F.append(reduce(lambda x,y: x*y, [F[x] for x in pfactors[j]]))
        yield tuple(F)


def GenGeneralFF(factors):
    for k in factors[0]:
        if len(factors) == 1:
            yield (k,)
        else:
            for l in GenGeneralFF(factors[1:]):
                yield (k,) + l


def FracFactorialDesignTest():
    Choice = "Production"
    if Choice == "Debug":
        ENDPOINT     = "192.168.1.10"
        INTERVAL     = 1
        COUNT        = 3
        TRADEOFF_TCP = True
        TRADEOFF_UDP = True
        pass
    elif Choice == "Production":
        ENDPOINT     = "192.168.1.10"
        INTERVAL     = 10
        COUNT        = 5
        TRADEOFF_TCP = True
        TRADEOFF_UDP = True
        pass

    kwds = {"Endpoint":         ENDPOINT,
            "Interval":         INTERVAL,
            "Count":            COUNT,
            "Style":            "P",
            "Tradeoff_TCPtest": TRADEOFF_TCP,
            "Tradeoff_UDPtest": TRADEOFF_UDP}

    A = {-1:"tapbr",  1:"tun"}
    B = {-1:"udp",    1:"tcp"}
    C = {-1:"noenc",  1:"aes256"}
    D = {-1:"nocomp", 1:"lzocomp"}
    E = {-1:"Text",   1:"Video"}
    dict = (A,B,C,D,E)

    k = 5
    p = 1
    pfactors = ((0,1,2,3),)
    G = list(GenFF(k=k, p=p, pfactors=pfactors))

    # Open the output file
    fo = open("perftest.out", "w", 1)

    # Tee the output
    stdout = sys.stdout
    sys.stdout = Tee(files=(stdout, fo))

    t0 = time.time()
    print "Start time:  %s" % time.asctime()

    try:
        # Run each performance test
        for i in range(2**(k-p)):
            SetupRunPerfTest(Interface=dict[0][G[i][0]], Protocol=dict[1][G[i][1]], Encryption=dict[2][G[i][2]], Compression=dict[3][G[i][3]], Workload=dict[4][G[i][4]], **kwds)
            fo.flush()
    finally:
        # Report the end time
        t1 = time.time()
        print "End time:  %s" % time.asctime()
        print ""
        print "Total elapsed time:  %.1f s" % (t1-t0)
        print "                     %d min %.1f s" % (int((t1-t0)//60), math.fmod(t1-t0, 60))

        # Restore the standard output
        sys.stdout = stdout

        # Close the output file
        fo.close()


def GeneralFactorialDesignTest():
    Choice = "Production"
    if Choice == "Debug":
        ENDPOINT     = "192.168.1.10"
        INTERVAL     = 1
        COUNT        = 3
        TRADEOFF_TCP = True
        TRADEOFF_UDP = True
        pass
    elif Choice == "Production":
        ENDPOINT     = "192.168.1.10"
        INTERVAL     = 10
        COUNT        = 5
        TRADEOFF_TCP = True
        TRADEOFF_UDP = True
        pass

    kwds = {"Endpoint":         ENDPOINT,
            "Interval":         INTERVAL,
            "Count":            COUNT,
            "Style":            "P",
            "Tradeoff_TCPtest": TRADEOFF_TCP,
            "Tradeoff_UDPtest": TRADEOFF_UDP}

    A = {1:"tapbr",  2:"tap",     3:"tun"}
    #A = {2:"tap",     3:"tun"}
    B = {1:"udp",    2:"tcp"}
    C = {1:"noenc",  2:"bf256",   3:"aes256"}
    D = {1:"nocomp", 2:"lzocomp"}
    E = {1:"Text",   2:"Video"}
    factors = (A,B,C,D,E)

    G = list(GenGeneralFF(factors))

    # Open the output file
    fo = open("perftest.out", "w", 1)

    # Tee the output
    stdout = sys.stdout
    sys.stdout = Tee(files=(stdout, fo))

    t0 = time.time()
    print "Start time:  %s" % time.asctime()

    try:
        # Run each performance test
        for i in range(len(G)):
            print ','.join([factors[x[0]][x[1]] for x in enumerate(G[i])])

            SetupRunPerfTest(Interface=factors[0][G[i][0]], Protocol=factors[1][G[i][1]], Encryption=factors[2][G[i][2]], Compression=factors[3][G[i][3]], Workload=factors[4][G[i][4]], **kwds)
            fo.flush()
    finally:
        # Report the end time
        t1 = time.time()
        print "End time:  %s" % time.asctime()
        print ""
        print "Total elapsed time:  %.1f s" % (t1-t0)
        print "                     %d min %.1f s" % (int((t1-t0)//60), math.fmod(t1-t0, 60))

        # Restore the standard output
        sys.stdout = stdout

        # Close the output file
        fo.close()


def OneShotPerfTest():
    Choice = "Debug"
    if Choice == "Debug":
        ENDPOINT     = "192.168.1.10"
        INTERFACE    = "tapbr"
        PROTOCOL     = "udp"
        COMPRESSION  = "nocomp"
        ENCRYPTION   = "noenc"
        INTERVAL     = 1
        COUNT        = 5
        STYLE        = "P"
        WORKLOAD     = "Video"
        PAYLOAD_LEN  = None
        TRADEOFF_TCP = True
        TRADEOFF_UDP = True
        pass
    elif Choice == "Production":
        ENDPOINT     = "192.168.1.10"
        INTERFACE    = "tun"
        PROTOCOL     = "udp"
        COMPRESSION  = "nocomp"
        ENCRYPTION   = "noenc"
        INTERVAL     = 10
        COUNT        = 5
        STYLE        = "B"
        WORKLOAD     = "Video"
        PAYLOAD_LEN  = None
        TRADEOFF_TCP = True
        TRADEOFF_UDP = True
        pass

    server_conf = ConfigBuilder(HostType='server', Interface=INTERFACE, Protocol=PROTOCOL, Compression=COMPRESSION, Encryption=ENCRYPTION)
    client_conf = ConfigBuilder(HostType='client', Interface=INTERFACE, Protocol=PROTOCOL, Compression=COMPRESSION, Encryption=ENCRYPTION)

    connected = False
    while not connected:
        server = OpenVPN_Server('192.168.2.1')
        server.connect()

        #while True:
            #try:
                #sys.stdout.write(os.read(server.P.stdout.fileno(), 1000))
            #except OSError:
                #pass

        server.kill_openvpn()
        server.start_openvpn(server_conf)

        client = OpenVPN_Client()
        client.kill_openvpn()
        client.start_openvpn(client_conf)

        time.sleep(10.0)

        print 'Server Output'
        print '-------------'
        print os.read(server.P.stdout.fileno(), 100000)
        print ''
        print 'Client Output'
        print '-------------'
        print os.read(client.P.stdout.fileno(), 100000)
        print ''

        print 'Ping Output'
        print '-----------'
        P = subprocess.Popen(['ping', '-c', '100', ENDPOINT], stdout=subprocess.PIPE)
        buf = ''
        ping_count = 0
        while P.poll() == None or len(buf) > 0:
            buf = os.read(P.stdout.fileno(), 1000)
            sys.stdout.write(buf)
            if len(re.findall('\d+ bytes from .*: icmp_seq=\d+ ttl=\d+ time=\d+\.\d+', buf)) > 0:
                ping_count += 1
                if ping_count >= 3:
                    connected = True
                    break
        try:
            os.kill(P.pid, signal.SIGTERM)
        except OSError:
            pass
        print ''

        if not connected:
            print 'No connection detected...restarting'

    # Estimate the expected test time
    estimated_test_time = INTERVAL*COUNT*(2 if TRADEOFF_TCP else 1) + (INTERVAL*(2 if TRADEOFF_UDP else 1)+1)*COUNT + INTERVAL*COUNT

    print "Server config:   %s"   % server_conf
    print "Client config:   %s"   % client_conf
    print ""
    print "Endpoint:        %s"   % ENDPOINT
    print "Interface:       %s"   % INTERFACE
    print "Protocol:        %s"   % PROTOCOL
    print "Compression:     %s"   % COMPRESSION
    print "Encryption:      %s"   % ENCRYPTION
    print "Interval:        %.1f" % INTERVAL
    print "Count:           %d"   % COUNT
    print "Workload:        %s"   % WORKLOAD
    print "Payload Length:  %s"   % str(PAYLOAD_LEN)
    print ""
    print "Estimated time:  %.1f s" % estimated_test_time
    print ""

    # Do performance test
    try:
        RunPerfTest(Endpoint=ENDPOINT, Interval=INTERVAL, Count=COUNT, Style=STYLE, Tradeoff_TCPtest=TRADEOFF_TCP, Tradeoff_UDPtest=TRADEOFF_UDP,
            Workload=WorkloadDict[WORKLOAD], PayloadLength=PAYLOAD_LEN, TunInt=InterfaceDict[INTERFACE])
    finally:
        server = None
        client = None


if __name__ == "__main__":
    OneShotPerfTest()
    #FracFactorialDesignTest()
    #GeneralFactorialDesignTest()

