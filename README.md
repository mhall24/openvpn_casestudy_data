# OpenVPN Case Study
Performance case study of OpenVPN on a consumer router (CSE 567M project data/code)

This repository contains data, experimental results, and supporting code for the class project paper titled:

**“Performance Case Study of OpenVPN on a Consumer Router”**  
CSE 567M: Computer Systems Analysis
Washington University in St. Louis – Fall 2008  
Instructor: Dr. Raj Jain  
Author: Michael J. Hall

The paper is available [on Dr. Jain's course website](https://www.cse.wustl.edu/~jain/cse567-08/ftp/ovpn/index.html) and will also be submitted to [arXiv](https://arxiv.org/).

## 📄 Overview

This project investigates the performance characteristics of OpenVPN running on a consumer-grade router under various configurations and workloads. The study focuses on throughput, CPU load, and latency impacts under different encryption modes, number of clients, and routing paths.

## 📁 Repository Contents

- `data/`  
  Raw and processed data from experiments, including throughput, latency, and CPU usage measurements.

- `scripts/`  
  Bash and Python scripts used to configure experiments, collect data, and generate plots.

- `figures/`  
  Figures and charts used in the paper.

- `configs/`  
  OpenVPN server and client configuration files used during testing.

## 🧪 Experimental Setup

The tests were conducted using a [Router Model Name] flashed with [OpenWRT/DD-WRT/stock firmware] and an OpenVPN server configured with [encryption method, cipher, etc.]. Client machines were connected over [Wi-Fi / Ethernet] and used to simulate realistic VPN traffic patterns using `iperf3`, `netperf`, and custom scripts.

See the `scripts/` and `configs/` folders for reproducibility details.

## 📊 Results Summary

The key findings of the study include:

- Throughput degradation under AES-256 encryption vs. AES-128.
- CPU bottlenecks on the router under multiple client loads.
- Trade-offs between UDP and TCP tunnel modes.
- Impact of routing VPN traffic through WAN vs LAN interfaces.

Detailed graphs and discussion are included in the paper and available under `figures/`.

## 📜 Citation

If you use this code or dataset, please cite the class paper or link back to this repository:

[Your Name], “Performance Case Study of OpenVPN on a Consumer Router,”
CSE 567M Class Project Paper, Washington University in St. Louis, Spring 2025.
Available: [URL to arXiv or Jain's site]

## 📄 License

This repository is released under the MIT License. See `LICENSE` for more information.
